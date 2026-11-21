#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d9.h>

#include <cstdio>
#include <cstring>

namespace
{
    bool ReadLog(char* buffer, DWORD capacity)
    {
        if (!buffer || capacity < 2)
            return false;

        HANDLE file = CreateFileW(
            L"build\\bin\\IVLegacy.log",
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            NULL,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            NULL);
        if (file == INVALID_HANDLE_VALUE)
            return false;

        DWORD read = 0;
        const BOOL ok = ReadFile(file, buffer, capacity - 1, &read, NULL);
        CloseHandle(file);
        if (!ok)
            return false;

        buffer[read] = '\0';
        return true;
    }

    bool WaitForLog(const char* marker, DWORD timeoutMs)
    {
        const DWORD start = GetTickCount();
        char buffer[32768] = {};

        do
        {
            if (ReadLog(buffer, sizeof(buffer)) && strstr(buffer, marker))
                return true;
            Sleep(50);
        } while (GetTickCount() - start < timeoutMs);

        return false;
    }

    bool HasEither(const char* first, const char* second)
    {
        char buffer[32768] = {};
        if (!ReadLog(buffer, sizeof(buffer)))
            return false;
        return strstr(buffer, first) != NULL || strstr(buffer, second) != NULL;
    }

    int Fail(const char* message)
    {
        std::fprintf(stderr, "FAIL: %s\n", message);
        char buffer[32768] = {};
        if (ReadLog(buffer, sizeof(buffer)))
            std::fprintf(stderr, "%s\n", buffer);
        return 1;
    }
}

int main()
{
    const wchar_t* iniPath = L"build\\bin\\IVLegacy.ini";
    WritePrivateProfileStringW(
        L"General", L"EnableD3D9Telemetry", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"StrictGTAIV100", L"1", iniPath);
    DeleteFileW(L"build\\bin\\IVLegacy.log");

    HMODULE asi = LoadLibraryW(L"build\\bin\\IVLegacyASI.asi");
    if (!asi)
        return Fail("LoadLibrary failed for IVLegacyASI.asi");

    if (!WaitForLog("D3D9_IAT_HOOK_INSTALLED", 10000))
        return Fail("ASI bootstrap did not install the Direct3DCreate9 IAT hook");

    IDirect3D9* d3d = Direct3DCreate9(D3D_SDK_VERSION);
    if (!d3d)
        return Fail("Direct3DCreate9 returned NULL");

    D3DADAPTER_IDENTIFIER9 identifier = {};
    const HRESULT identifierHr = d3d->GetAdapterIdentifier(0, 0, &identifier);

    D3DCAPS9 caps = {};
    const HRESULT capsHr = d3d->GetDeviceCaps(0, D3DDEVTYPE_HAL, &caps);

    d3d->Release();

    if (!WaitForLog("DIRECT3DCREATE9", 5000))
        return Fail("Direct3DCreate9 wrapper was not called");
    if (!HasEither("D3D9_ADAPTER adapter=", "D3D9_ADAPTER_IDENTIFIER_FAILED"))
        return Fail("IDirect3D9::GetAdapterIdentifier hook was not observed");
    if (!HasEither("D3D9_GET_DEVICE_CAPS adapter=", "D3D9_GET_DEVICE_CAPS_FAILED"))
        return Fail("IDirect3D9::GetDeviceCaps hook was not observed");

    char buffer[32768] = {};
    ReadLog(buffer, sizeof(buffer));
    std::printf("PASS: ASI loaded and D3D9 interface hooks executed.\n");
    std::printf("GetAdapterIdentifier HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(identifierHr));
    std::printf("GetDeviceCaps HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(capsHr));
    std::printf("%s\n", buffer);

    // The ASI remains loaded until process exit because its IAT/vtable hooks
    // point into the module; hot-unloading it would leave dangling callbacks.
    (void)asi;
    return 0;
}
