#!/usr/bin/env python3
"""Read-only PE32 import inspection for the original GTA IV 1.0.0.0 executable.

The tool distinguishes normal and delay imports of d3d9.dll!Direct3DCreate9.
The current ASI hook scans only the main executable's normal import table and
requires a non-zero OriginalFirstThunk lookup table. Static imports do not prove
that a later dynamic GetProcAddress path is unused.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IMAGE_FILE_MACHINE_I386 = 0x014C
IMAGE_NT_OPTIONAL_HDR32_MAGIC = 0x010B
IMAGE_DIRECTORY_ENTRY_IMPORT = 1
IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT = 13
IMAGE_ORDINAL_FLAG32 = 0x80000000


class PEFormatError(ValueError):
    """Raised when a PE image or one of its import structures is malformed."""


@dataclass(frozen=True)
class Section:
    name: str
    virtual_size: int
    virtual_address: int
    raw_size: int
    raw_offset: int


class PE32Image:
    def __init__(self, data: bytes):
        self.data = data
        self.sections: list[Section] = []
        self.machine = 0
        self.timestamp = 0
        self.entry_point = 0
        self.image_base = 0
        self.size_of_image = 0
        self.size_of_headers = 0
        self.directories: list[tuple[int, int]] = []
        self._parse_headers()

    def _need(self, offset: int, size: int, label: str) -> None:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise PEFormatError(f"{label} lies outside the file")

    def _u16(self, offset: int, label: str) -> int:
        self._need(offset, 2, label)
        return struct.unpack_from("<H", self.data, offset)[0]

    def _u32(self, offset: int, label: str) -> int:
        self._need(offset, 4, label)
        return struct.unpack_from("<I", self.data, offset)[0]

    def _parse_headers(self) -> None:
        self._need(0, 0x40, "DOS header")
        if self.data[:2] != b"MZ":
            raise PEFormatError("missing MZ DOS signature")
        pe_offset = self._u32(0x3C, "e_lfanew")
        self._need(pe_offset, 24, "PE signature and COFF header")
        if self.data[pe_offset:pe_offset + 4] != b"PE\0\0":
            raise PEFormatError("missing PE signature")

        coff = pe_offset + 4
        self.machine = self._u16(coff, "COFF machine")
        section_count = self._u16(coff + 2, "section count")
        self.timestamp = self._u32(coff + 4, "COFF timestamp")
        optional_size = self._u16(coff + 16, "optional-header size")
        optional = coff + 20
        self._need(optional, optional_size, "optional header")

        magic = self._u16(optional, "optional-header magic")
        if magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC:
            raise PEFormatError(
                f"expected PE32 optional header 0x10B, found 0x{magic:04X}"
            )
        if self.machine != IMAGE_FILE_MACHINE_I386:
            raise PEFormatError(
                f"expected x86 machine 0x014C, found 0x{self.machine:04X}"
            )
        if optional_size < 96:
            raise PEFormatError("PE32 optional header is too short for data directories")

        self.entry_point = self._u32(optional + 16, "AddressOfEntryPoint")
        self.image_base = self._u32(optional + 28, "ImageBase")
        self.size_of_image = self._u32(optional + 56, "SizeOfImage")
        self.size_of_headers = self._u32(optional + 60, "SizeOfHeaders")
        directory_count = self._u32(optional + 92, "NumberOfRvaAndSizes")
        directory_offset = optional + 96
        available_directories = max(0, (optional_size - 96) // 8)
        count = min(directory_count, available_directories)
        for index in range(count):
            rva, size = struct.unpack_from("<II", self.data, directory_offset + index * 8)
            self.directories.append((rva, size))

        section_table = optional + optional_size
        self._need(section_table, section_count * 40, "section table")
        for index in range(section_count):
            offset = section_table + index * 40
            raw_name = self.data[offset:offset + 8].split(b"\0", 1)[0]
            name = raw_name.decode("ascii", errors="replace")
            virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from(
                "<IIII", self.data, offset + 8
            )
            self.sections.append(Section(
                name, virtual_size, virtual_address, raw_size, raw_offset
            ))

        if self.size_of_headers > len(self.data):
            raise PEFormatError("SizeOfHeaders exceeds file length")

    def directory(self, index: int) -> tuple[int, int]:
        if index >= len(self.directories):
            return (0, 0)
        return self.directories[index]

    def rva_to_offset(self, rva: int, size: int = 1) -> int:
        if rva < 0 or size < 0:
            raise PEFormatError("negative RVA or size")
        if rva < self.size_of_headers:
            self._need(rva, size, f"header RVA 0x{rva:X}")
            return rva

        for section in self.sections:
            extent = max(section.virtual_size, section.raw_size)
            if section.virtual_address <= rva < section.virtual_address + extent:
                delta = rva - section.virtual_address
                if delta + size > section.raw_size:
                    raise PEFormatError(
                        f"RVA 0x{rva:X} points beyond raw data in section {section.name}"
                    )
                offset = section.raw_offset + delta
                self._need(offset, size, f"RVA 0x{rva:X}")
                return offset
        raise PEFormatError(f"RVA 0x{rva:X} is not mapped by any section")

    def read_c_string(self, rva: int, max_length: int = 4096) -> str:
        offset = self.rva_to_offset(rva, 1)
        end = min(len(self.data), offset + max_length)
        nul = self.data.find(b"\0", offset, end)
        if nul < 0:
            raise PEFormatError(f"unterminated string at RVA 0x{rva:X}")
        return self.data[offset:nul].decode("ascii", errors="replace")

    def _read_thunks(
        self,
        names_rva: int,
        iat_rva: int,
        *,
        max_thunks: int = 8192,
    ) -> list[dict[str, Any]]:
        if names_rva == 0:
            return []
        imports: list[dict[str, Any]] = []
        for index in range(max_thunks):
            lookup_rva = names_rva + index * 4
            lookup_offset = self.rva_to_offset(lookup_rva, 4)
            thunk = struct.unpack_from("<I", self.data, lookup_offset)[0]
            if thunk == 0:
                return imports
            iat_entry_rva = iat_rva + index * 4 if iat_rva else None

            if thunk & IMAGE_ORDINAL_FLAG32:
                imports.append({
                    "kind": "ordinal",
                    "ordinal": thunk & 0xFFFF,
                    "name": None,
                    "hint": None,
                    "lookup_rva": lookup_rva,
                    "iat_rva": iat_entry_rva,
                })
            else:
                name_offset = self.rva_to_offset(thunk, 3)
                hint = struct.unpack_from("<H", self.data, name_offset)[0]
                name_rva = thunk + 2
                name = self.read_c_string(name_rva)
                imports.append({
                    "kind": "name",
                    "name": name,
                    "hint": hint,
                    "ordinal": None,
                    "lookup_rva": lookup_rva,
                    "iat_rva": iat_entry_rva,
                })
        raise PEFormatError(
            f"thunk table at RVA 0x{names_rva:X} has no null terminator within {max_thunks} entries"
        )

    def normal_imports(self) -> list[dict[str, Any]]:
        rva, size = self.directory(IMAGE_DIRECTORY_ENTRY_IMPORT)
        if rva == 0 or size == 0:
            return []
        if size < 20:
            raise PEFormatError("import directory is too small for a descriptor")

        imports: list[dict[str, Any]] = []
        descriptor_count = min(size // 20, 4096)
        found_terminator = False
        for index in range(descriptor_count):
            desc_rva = rva + index * 20
            desc_offset = self.rva_to_offset(desc_rva, 20)
            oft, timestamp, forwarder, name_rva, first_thunk = struct.unpack_from(
                "<IIIII", self.data, desc_offset
            )
            if not (oft or timestamp or forwarder or name_rva or first_thunk):
                found_terminator = True
                break
            if name_rva == 0:
                raise PEFormatError(f"import descriptor {index} has no DLL name")
            dll = self.read_c_string(name_rva)
            lookup_rva = oft or first_thunk
            for item in self._read_thunks(lookup_rva, first_thunk):
                item.update({
                    "dll": dll,
                    "table": "normal",
                    "descriptor_index": index,
                    "original_first_thunk_rva": oft,
                    "first_thunk_rva": first_thunk,
                })
                imports.append(item)
        if not found_terminator:
            raise PEFormatError("import descriptor table has no null terminator")
        return imports

    def delay_imports(self) -> list[dict[str, Any]]:
        rva, size = self.directory(IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT)
        if rva == 0 or size == 0:
            return []
        if size < 32:
            raise PEFormatError("delay-import directory is too small for a descriptor")

        imports: list[dict[str, Any]] = []
        descriptor_count = min(size // 32, 4096)
        found_terminator = False
        for index in range(descriptor_count):
            desc_offset = self.rva_to_offset(rva + index * 32, 32)
            fields = struct.unpack_from("<IIIIIIII", self.data, desc_offset)
            attrs, name_field, _module_handle, iat_field, int_field, _bound, _unload, _timestamp = fields
            if not any(fields):
                found_terminator = True
                break

            rva_based = (attrs & 1) != 0
            def convert(value: int) -> int:
                if value == 0 or rva_based:
                    return value
                if value < self.image_base:
                    raise PEFormatError("delay-import VA is below the PE image base")
                return value - self.image_base

            name_rva = convert(name_field)
            iat_rva = convert(iat_field)
            int_rva = convert(int_field) or iat_rva
            if name_rva == 0:
                raise PEFormatError(f"delay-import descriptor {index} has no DLL name")
            dll = self.read_c_string(name_rva)
            for item in self._read_thunks(int_rva, iat_rva):
                item.update({
                    "dll": dll,
                    "table": "delay",
                    "descriptor_index": index,
                })
                imports.append(item)
        if not found_terminator:
            raise PEFormatError("delay-import descriptor table has no null terminator")
        return imports


def assess_factory_hook_path(
    normal_imports: list[dict[str, Any]],
    delay_imports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assess only the static import route implemented by the current ASI."""
    def is_factory(item: dict[str, Any]) -> bool:
        return (
            item.get("dll", "").lower() == "d3d9.dll"
            and item.get("name") == "Direct3DCreate9"
        )

    normal_factory = [item for item in normal_imports if is_factory(item)]
    delay_factory = [item for item in delay_imports if is_factory(item)]
    normal_with_lookup = [
        item for item in normal_factory
        if (
            int(item.get("original_first_thunk_rva") or 0) != 0
            and int(item.get("first_thunk_rva") or 0) != 0
        )
    ]

    if normal_with_lookup:
        if delay_factory:
            classification = "normal_iat_candidate_plus_delay_import"
            message = (
                "a supported normal-IAT candidate exists, but any delay-import "
                "call path is not hooked by the current ASI"
            )
        else:
            classification = "normal_iat_candidate"
            message = (
                "a supported normal-IAT candidate exists; actual runtime use "
                "and ASI load timing still need verification"
            )
    elif normal_factory:
        classification = "normal_import_without_lookup_table"
        message = (
            "Direct3DCreate9 is a normal import, but OriginalFirstThunk is zero; "
            "the current ASI skips this descriptor"
        )
    elif delay_factory:
        classification = "delay_import_only"
        message = (
            "Direct3DCreate9 appears only in the delay-import table; the current "
            "ASI scans normal imports only and will not hook this route"
        )
    else:
        classification = "no_direct_normal_import"
        message = (
            "no direct normal Direct3DCreate9 import with a usable lookup table "
            "was found; dynamic resolution or another module remains possible"
        )

    return {
        "classification": classification,
        "hook_candidate": bool(normal_with_lookup),
        "normal_direct_import_count": len(normal_factory),
        "delay_direct_import_count": len(delay_factory),
        "normal_direct_imports_with_lookup_table": len(normal_with_lookup),
        "message": message,
    }


def get_windows_file_version(path: Path) -> tuple[str | None, str]:
    """Read VS_FIXEDFILEINFO using the Windows version APIs."""
    if os.name != "nt":
        return None, "unavailable_non_windows"
    try:
        version = ctypes.WinDLL("version", use_last_error=True)
        get_size = version.GetFileVersionInfoSizeW
        get_size.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
        get_size.restype = ctypes.c_uint32

        get_info = version.GetFileVersionInfoW
        get_info.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p
        ]
        get_info.restype = ctypes.c_int

        query = version.VerQueryValueW
        query.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)
        ]
        query.restype = ctypes.c_int

        handle = ctypes.c_uint32(0)
        size = get_size(str(path), ctypes.byref(handle))
        if not size:
            return None, f"missing_version_resource_winerror_{ctypes.get_last_error()}"
        buffer = ctypes.create_string_buffer(size)
        if not get_info(str(path), 0, size, buffer):
            return None, f"GetFileVersionInfo_failed_winerror_{ctypes.get_last_error()}"

        value = ctypes.c_void_p()
        value_length = ctypes.c_uint32()
        if not query(buffer, "\\", ctypes.byref(value), ctypes.byref(value_length)):
            return None, f"VerQueryValue_failed_winerror_{ctypes.get_last_error()}"
        if value_length.value < 16:
            return None, "VS_FIXEDFILEINFO_too_short"

        file_version_ms = ctypes.c_uint32.from_address(value.value + 8).value
        file_version_ls = ctypes.c_uint32.from_address(value.value + 12).value
        parts = (
            (file_version_ms >> 16) & 0xFFFF,
            file_version_ms & 0xFFFF,
            (file_version_ls >> 16) & 0xFFFF,
            file_version_ls & 0xFFFF,
        )
        return ".".join(str(x) for x in parts), "ok"
    except Exception as exc:  # WinAPI availability differs by Python/Windows build.
        return None, f"version_api_error:{exc}"


def inspect_file(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    pe = PE32Image(data)
    normal = pe.normal_imports()
    delay = pe.delay_imports()
    all_imports = normal + delay

    relevant = []
    for item in all_imports:
        dll = item["dll"].lower()
        name = item.get("name")
        if dll == "d3d9.dll" or name in (
            "Direct3DCreate9", "Direct3DCreate9Ex", "GetProcAddress"
        ):
            relevant.append(item)

    d3d9_imports = [
        item for item in all_imports if item["dll"].lower() == "d3d9.dll"
    ]
    direct_factory = [
        item for item in d3d9_imports
        if item.get("name") == "Direct3DCreate9"
    ]
    direct_factory_ex = [
        item for item in d3d9_imports
        if item.get("name") == "Direct3DCreate9Ex"
    ]
    normal_factory = [item for item in direct_factory if item["table"] == "normal"]
    delay_factory = [item for item in direct_factory if item["table"] == "delay"]
    normal_factory_with_lookup = [
        item for item in normal_factory
        if (
            int(item.get("original_first_thunk_rva") or 0) != 0
            and int(item.get("first_thunk_rva") or 0) != 0
        )
    ]
    hook_path = assess_factory_hook_path(normal, delay)
    get_proc_address = [
        item for item in all_imports
        if item.get("name") == "GetProcAddress"
    ]

    file_version, version_status = get_windows_file_version(path)
    return {
        "file": str(path),
        "file_name": path.name,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "machine": f"0x{pe.machine:04X}",
        "machine_name": "IMAGE_FILE_MACHINE_I386",
        "optional_header": "PE32",
        "timestamp": pe.timestamp,
        "entry_point_rva": f"0x{pe.entry_point:08X}",
        "image_base": f"0x{pe.image_base:08X}",
        "size_of_image": pe.size_of_image,
        "section_count": len(pe.sections),
        "sections": [
            {
                "name": section.name,
                "virtual_address": f"0x{section.virtual_address:08X}",
                "virtual_size": section.virtual_size,
                "raw_size": section.raw_size,
            }
            for section in pe.sections
        ],
        "file_version": file_version,
        "file_version_status": version_status,
        "expected_original_version": "1.0.0.0",
        "is_original_version_by_resource": file_version == "1.0.0.0",
        "normal_import_count": len(normal),
        "delay_import_count": len(delay),
        "imports_d3d9_dll": [
            {
                "name": x.get("name"),
                "kind": x["kind"],
                "table": x["table"],
                "lookup_rva": f"0x{x['lookup_rva']:08X}",
                "original_first_thunk_rva": (
                    f"0x{x['original_first_thunk_rva']:08X}"
                    if "original_first_thunk_rva" in x else None
                ),
                "first_thunk_rva": (
                    f"0x{x['first_thunk_rva']:08X}"
                    if "first_thunk_rva" in x else None
                ),
            }
            for x in d3d9_imports
        ],
        "direct3dcreate9_normal_or_delay_import": bool(direct_factory),
        "direct3dcreate9_normal_import": bool(normal_factory),
        "direct3dcreate9_delay_import": bool(delay_factory),
        "direct3dcreate9_normal_import_with_lookup_table": bool(normal_factory_with_lookup),
        "direct3dcreate9_hook_candidate": hook_path["hook_candidate"],
        "direct3dcreate9ex_normal_or_delay_import": bool(direct_factory_ex),
        "getprocaddress_import_present": bool(get_proc_address),
        "relevant_imports": [
            {
                "dll": x["dll"],
                "name": x.get("name"),
                "ordinal": x.get("ordinal"),
                "table": x["table"],
            }
            for x in relevant
        ],
        "hook_assessment_code": hook_path["classification"],
        "hook_assessment": hook_path["message"],
        "hook_assessment_counts": {
            "normal_direct_import_count": hook_path["normal_direct_import_count"],
            "delay_direct_import_count": hook_path["delay_direct_import_count"],
            "normal_direct_imports_with_lookup_table":
                hook_path["normal_direct_imports_with_lookup_table"],
        },
        "limitations": [
            "The current ASI scans only the main executable's normal import table.",
            "The current ASI skips a D3D9 import descriptor when OriginalFirstThunk is zero.",
            "The current ASI does not patch delay imports or Direct3DCreate9Ex.",
            "A PE import table cannot prove whether a later GetProcAddress call resolves D3D9 dynamically; importing GetProcAddress does not prove that it is used for D3D9.",
            "A D3D9 import from another module is outside the current main-executable IAT hook.",
            "The tool reads the executable; it never modifies the file."
        ],
    }


def _synthetic_pe32() -> bytes:
    data = bytearray(0x400)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"

    # COFF header.
    struct.pack_into(
        "<HHIIIHH",
        data, 0x84,
        IMAGE_FILE_MACHINE_I386, 1, 0x65432100, 0, 0, 224, 0x0102
    )

    optional = 0x98
    struct.pack_into("<H", data, optional, IMAGE_NT_OPTIONAL_HDR32_MAGIC)
    struct.pack_into("<I", data, optional + 16, 0x1000)    # entry point
    struct.pack_into("<I", data, optional + 28, 0x400000)  # image base
    struct.pack_into("<I", data, optional + 32, 0x1000)    # section alignment
    struct.pack_into("<I", data, optional + 36, 0x200)     # file alignment
    struct.pack_into("<I", data, optional + 56, 0x2000)    # image size
    struct.pack_into("<I", data, optional + 60, 0x200)     # header size
    struct.pack_into("<I", data, optional + 92, 16)        # directory count
    struct.pack_into("<II", data, optional + 96 + 8, 0x1000, 40)  # imports

    # One .idata section.
    section = optional + 224
    data[section:section + 8] = b".idata\0\0"
    struct.pack_into("<IIII", data, section + 8, 0x200, 0x1000, 0x200, 0x200)

    # IMAGE_IMPORT_DESCRIPTOR at RVA 0x1000 -> file offset 0x200.
    struct.pack_into("<IIIII", data, 0x200, 0x1040, 0, 0, 0x1028, 0x1060)
    data[0x228:0x231] = b"d3d9.dll\0"
    struct.pack_into("<II", data, 0x240, 0x1080, 0)  # OriginalFirstThunk
    struct.pack_into("<II", data, 0x260, 0x1080, 0)  # FirstThunk
    struct.pack_into("<H", data, 0x280, 0)            # Hint
    data[0x282:0x292] = b"Direct3DCreate9\0"
    return bytes(data)


def _self_test() -> None:
    pe = PE32Image(_synthetic_pe32())
    imports = pe.normal_imports()
    assert len(imports) == 1
    assert imports[0]["dll"].lower() == "d3d9.dll"
    assert imports[0]["name"] == "Direct3DCreate9"
    assert imports[0]["table"] == "normal"
    assert imports[0]["original_first_thunk_rva"] == 0x1040
    assert imports[0]["first_thunk_rva"] == 0x1060

    # Exercise the real PE parser's OFT==0 fallback to FirstThunk. The
    # on-disk IAT contains name RVAs before the Windows loader resolves it.
    oft_zero_image = bytearray(_synthetic_pe32())
    struct.pack_into("<I", oft_zero_image, 0x200, 0)
    oft_zero_imports = PE32Image(bytes(oft_zero_image)).normal_imports()
    assert len(oft_zero_imports) == 1
    assert oft_zero_imports[0]["name"] == "Direct3DCreate9"
    assert oft_zero_imports[0]["original_first_thunk_rva"] == 0
    oft_zero_assessment = assess_factory_hook_path(oft_zero_imports, [])
    assert oft_zero_assessment["classification"] == "normal_import_without_lookup_table"
    assert oft_zero_assessment["hook_candidate"] is False

    # A non-zero OriginalFirstThunk is not enough if the actual IAT RVA is
    # absent: the current ASI writes its replacement into FirstThunk.
    missing_iat_image = bytearray(_synthetic_pe32())
    struct.pack_into("<I", missing_iat_image, 0x210, 0)
    missing_iat_imports = PE32Image(bytes(missing_iat_image)).normal_imports()
    assert len(missing_iat_imports) == 1
    assert missing_iat_imports[0]["original_first_thunk_rva"] == 0x1040
    assert missing_iat_imports[0]["first_thunk_rva"] == 0
    missing_iat_assessment = assess_factory_hook_path(missing_iat_imports, [])
    assert missing_iat_assessment["classification"] == "normal_import_without_lookup_table"
    assert missing_iat_assessment["hook_candidate"] is False

    normal_candidate = assess_factory_hook_path(imports, [])
    assert normal_candidate["classification"] == "normal_iat_candidate"
    assert normal_candidate["hook_candidate"] is True

    delay_only = assess_factory_hook_path([], [{
        "dll": "d3d9.dll", "name": "Direct3DCreate9", "table": "delay"
    }])
    assert delay_only["classification"] == "delay_import_only"
    assert delay_only["hook_candidate"] is False

    missing_lookup = assess_factory_hook_path([{
        "dll": "d3d9.dll", "name": "Direct3DCreate9",
        "table": "normal", "original_first_thunk_rva": 0
    }], [])
    assert missing_lookup["classification"] == "normal_import_without_lookup_table"
    assert missing_lookup["hook_candidate"] is False

    mixed_paths = assess_factory_hook_path(imports, [{
        "dll": "d3d9.dll", "name": "Direct3DCreate9", "table": "delay"
    }])
    assert mixed_paths["classification"] == "normal_iat_candidate_plus_delay_import"
    assert mixed_paths["hook_candidate"] is True

    try:
        PE32Image(b"not a PE file")
    except PEFormatError:
        pass
    else:
        raise AssertionError("malformed input must be rejected")

    print("PASS: PE32 x86 import-table inspection self-tests")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", nargs="?", type=Path)
    parser.add_argument("--json", type=Path, help="Write the full JSON inspection report")
    parser.add_argument("--require-version", default="1.0.0.0")
    parser.add_argument("--skip-version-check", action="store_true",
                        help="Only inspect PE/import data; do not require a Windows file-version resource")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return 0
    if args.executable is None:
        parser.error("executable is required unless --self-test is used")
    if not args.executable.is_file():
        print(f"ERROR: file not found: {args.executable}", file=sys.stderr)
        return 2

    try:
        report = inspect_file(args.executable)
    except (OSError, PEFormatError, struct.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"File: {report['file_name']}")
    print(f"SHA-256: {report['sha256']}")
    print(f"PE: {report['optional_header']} {report['machine_name']}")
    print(f"File version: {report['file_version'] or report['file_version_status']}")
    print(f"Normal imports: {report['normal_import_count']}; delay imports: {report['delay_import_count']}")
    print(f"d3d9.dll imports: {report['imports_d3d9_dll']}")
    print(
        "Direct Direct3DCreate9 imports: "
        f"normal={report['direct3dcreate9_normal_import']}, "
        f"delay={report['direct3dcreate9_delay_import']}, "
        f"normal_with_lookup_table={report['direct3dcreate9_normal_import_with_lookup_table']}"
    )
    print(f"Direct Direct3DCreate9Ex import: {report['direct3dcreate9ex_normal_or_delay_import']}")
    print(f"GetProcAddress import present: {report['getprocaddress_import_present']}")
    print(f"Hook assessment [{report['hook_assessment_code']}]: {report['hook_assessment']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"JSON report: {args.json}")

    if not args.skip_version_check:
        if report["file_version"] is None:
            print(
                "ERROR: original 1.0.0.0 file version could not be verified. "
                "Run this utility on Windows or use --skip-version-check for import-only inspection.",
                file=sys.stderr,
            )
            return 3
        if report["file_version"] != args.require_version:
            print(
                f"ERROR: expected file version {args.require_version}, "
                f"found {report['file_version']}",
                file=sys.stderr,
            )
            return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
