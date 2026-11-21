#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d9.h>

#include <cstdio>
#include <cstring>
#include <cstdlib>

namespace
{
    struct FakeComObject
    {
        void** vtable;
    };

    void* g_fakeD3D9VTable[17] = {};
    void* g_fakeDeviceVTable[119] = {};
    FakeComObject g_fakeD3D9 = {};
    FakeComObject g_fakeDevice = {};
    FakeComObject g_fakeVertexShader = {};
    FakeComObject g_fakePixelShaderObjects[4] = {};
    FakeComObject g_fakeTexture = {};
    FakeComObject g_fakeVertexDeclaration = {};
    FakeComObject g_fakeVertexBuffer = {};
    FakeComObject g_fakeIndexBuffer = {};
    void* g_fakeShaderVTable[3] = {};
    void* g_fakeTextureVTable[3] = {};
    DWORD g_fakeLastPixelShaderVersion = 0;
    volatile LONG g_fakePixelShaderCreateCount = 0;
    volatile LONG g_fakePixelShaderObjectCount = 0;
    DWORD g_syntheticPs3PixelShader[18] = {};
    DWORD g_syntheticPs3PixelShaderAlt[18] = {};

    DWORD MakeShaderRegisterToken(DWORD registerType, DWORD registerIndex)
    {
        return 0x80000000UL
            | ((registerIndex & 0x7FFUL))
            | (0xFUL << 16)
            | ((registerType & 0x7UL) << 28)
            | ((registerType & 0x18UL) << 8);
    }

    DWORD MakeShaderSourceToken(
        DWORD registerType,
        DWORD registerIndex,
        DWORD swizzle = 0xE4)
    {
        return 0x80000000UL
            | ((registerIndex & 0x7FFUL))
            | ((swizzle & 0xFFUL) << 16)
            | ((registerType & 0x7UL) << 28)
            | ((registerType & 0x18UL) << 8);
    }

    void BuildSyntheticPs3Shader()
    {
        DWORD index = 0;
        g_syntheticPs3PixelShader[index++] = 0xFFFF0300UL;
        g_syntheticPs3PixelShader[index++] = (2UL << 24) | 31UL;
        g_syntheticPs3PixelShader[index++] = 5UL;
        g_syntheticPs3PixelShader[index++] = MakeShaderRegisterToken(1, 0);
        g_syntheticPs3PixelShader[index++] = (2UL << 24) | 31UL;
        g_syntheticPs3PixelShader[index++] = (2UL << 27);
        g_syntheticPs3PixelShader[index++] = MakeShaderRegisterToken(10, 0);
        g_syntheticPs3PixelShader[index++] = (2UL << 24) | 1UL;
        g_syntheticPs3PixelShader[index++] = MakeShaderRegisterToken(0, 0);
        g_syntheticPs3PixelShader[index++] = MakeShaderSourceToken(1, 0);
        g_syntheticPs3PixelShader[index++] = (3UL << 24) | 66UL;
        g_syntheticPs3PixelShader[index++] = MakeShaderRegisterToken(0, 1);
        g_syntheticPs3PixelShader[index++] = MakeShaderSourceToken(0, 0);
        g_syntheticPs3PixelShader[index++] = MakeShaderSourceToken(10, 0);
        g_syntheticPs3PixelShader[index++] = (2UL << 24) | 1UL;
        g_syntheticPs3PixelShader[index++] = MakeShaderRegisterToken(8, 0);
        g_syntheticPs3PixelShader[index++] = MakeShaderSourceToken(0, 1);
        g_syntheticPs3PixelShader[index++] = 0x0000FFFFUL;

        if (index != _countof(g_syntheticPs3PixelShader))
            std::abort();

        CopyMemory(
            g_syntheticPs3PixelShaderAlt,
            g_syntheticPs3PixelShader,
            sizeof(g_syntheticPs3PixelShader));
        g_syntheticPs3PixelShaderAlt[16] = MakeShaderSourceToken(0, 1, 0x55);
    }

    unsigned __int64 HashShaderBytes(const BYTE* bytes, DWORD byteCount)
    {
        unsigned __int64 hash = 14695981039346656037ULL;
        for (DWORD i = 0; i < byteCount; ++i)
        {
            hash ^= bytes[i];
            hash *= 1099511628211ULL;
        }
        return hash;
    }

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

    bool HasText(const char* marker)
    {
        char buffer[32768] = {};
        if (!ReadLog(buffer, sizeof(buffer)))
            return false;
        return strstr(buffer, marker) != NULL;
    }

    void SmokeMark(const char* message)
    {
        std::fprintf(stderr, "SMOKE: %s\n", message);
        std::fflush(stderr);
    }

    LONG WINAPI SmokeUnhandledExceptionFilter(EXCEPTION_POINTERS* exception)
    {
        const DWORD code = exception && exception->ExceptionRecord
            ? exception->ExceptionRecord->ExceptionCode : 0;
        const void* address = exception && exception->ExceptionRecord
            ? exception->ExceptionRecord->ExceptionAddress : NULL;
        std::fprintf(stderr,
            "SMOKE_UNHANDLED_EXCEPTION code=0x%08lX address=%p\n",
            static_cast<unsigned long>(code), address);
        std::fflush(stderr);

        char logBuffer[32768] = {};
        if (ReadLog(logBuffer, sizeof(logBuffer)))
        {
            std::fprintf(stderr, "SMOKE_LOG_DUMP_BEGIN\n%s\nSMOKE_LOG_DUMP_END\n",
                logBuffer);
            std::fflush(stderr);
        }
        return EXCEPTION_EXECUTE_HANDLER;
    }

    int Fail(const char* message)
    {
        std::fprintf(stderr, "FAIL: %s\n", message);
        char buffer[32768] = {};
        if (ReadLog(buffer, sizeof(buffer)))
            std::fprintf(stderr, "%s\n", buffer);
        return 1;
    }

    HRESULT WINAPI FakeQueryInterface(void*, REFIID, void** output)
    {
        if (output)
            *output = NULL;
        return E_NOINTERFACE;
    }

    ULONG WINAPI FakeAddRef(void*)
    {
        return 1;
    }

    ULONG WINAPI FakeRelease(void*)
    {
        return 1;
    }

    HRESULT WINAPI FakeUnused()
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeGetAdapterIdentifier(
        IDirect3D9*,
        UINT,
        DWORD,
        D3DADAPTER_IDENTIFIER9* identifier)
    {
        if (!identifier)
            return D3DERR_INVALIDCALL;

        ZeroMemory(identifier, sizeof(*identifier));
        strcpy_s(identifier->Description, "Synthetic GMA 3100 test adapter");
        strcpy_s(identifier->Driver, "IVLegacy synthetic D3D9 test");
        identifier->VendorId = 0x8086;
        identifier->DeviceId = 0x29C2;
        identifier->SubSysId = 0;
        identifier->Revision = 1;
        identifier->DriverVersion.HighPart = 1;
        identifier->DriverVersion.LowPart = 1;
        return D3D_OK;
    }

    void FillFakeCaps(D3DCAPS9* caps)
    {
        if (!caps)
            return;

        ZeroMemory(caps, sizeof(*caps));
        caps->DeviceType = D3DDEVTYPE_HAL;
        caps->AdapterOrdinal = 0;
        caps->Caps = D3DCAPS_READ_SCANLINE;
        caps->MaxTextureWidth = 2048;
        caps->MaxTextureHeight = 2048;
        caps->MaxSimultaneousTextures = 2;
        caps->MaxTextureBlendStages = 2;
        caps->NumSimultaneousRTs = 1;
        caps->MaxVertexShaderConst = 96;
        caps->VertexShaderVersion = D3DVS_VERSION(2, 0);
        caps->PixelShaderVersion = D3DPS_VERSION(2, 0);
        caps->VS20Caps.NumTemps = 12;
        caps->VS20Caps.DynamicFlowControlDepth = 0;
        caps->VS20Caps.StaticFlowControlDepth = 1;
        caps->PS20Caps.NumTemps = 12;
        caps->PS20Caps.NumInstructionSlots = 96;
        caps->PS20Caps.DynamicFlowControlDepth = 0;
        caps->PS20Caps.StaticFlowControlDepth = 0;
    }

    HRESULT WINAPI FakeGetDeviceCaps(
        IDirect3D9*,
        UINT,
        D3DDEVTYPE,
        D3DCAPS9* caps)
    {
        if (!caps)
            return D3DERR_INVALIDCALL;
        FillFakeCaps(caps);
        return D3D_OK;
    }

    HRESULT WINAPI FakeCheckDeviceFormat(
        IDirect3D9*,
        UINT,
        D3DDEVTYPE,
        D3DFORMAT,
        DWORD,
        D3DRESOURCETYPE,
        D3DFORMAT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeCheckDepthStencilMatch(
        IDirect3D9*,
        UINT,
        D3DDEVTYPE,
        D3DFORMAT,
        D3DFORMAT,
        D3DFORMAT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceGetDeviceCaps(
        IDirect3DDevice9*,
        D3DCAPS9* caps)
    {
        if (!caps)
            return D3DERR_INVALIDCALL;
        FillFakeCaps(caps);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceReset(
        IDirect3DDevice9*,
        D3DPRESENT_PARAMETERS*)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDevicePresent(
        IDirect3DDevice9*,
        const RECT*,
        const RECT*,
        HWND,
        const RGNDATA*)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceCreateRenderTarget(
        IDirect3DDevice9*,
        UINT,
        UINT,
        D3DFORMAT,
        D3DMULTISAMPLE_TYPE,
        DWORD,
        BOOL,
        IDirect3DSurface9** surface,
        HANDLE*)
    {
        if (surface)
            *surface = NULL;
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceCreateDepthStencilSurface(
        IDirect3DDevice9*,
        UINT,
        UINT,
        D3DFORMAT,
        D3DMULTISAMPLE_TYPE,
        DWORD,
        BOOL,
        IDirect3DSurface9** surface,
        HANDLE*)
    {
        if (surface)
            *surface = NULL;
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetRenderTarget(
        IDirect3DDevice9*,
        DWORD,
        IDirect3DSurface9*)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetDepthStencilSurface(
        IDirect3DDevice9*,
        IDirect3DSurface9*)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceCreateVertexShader(
        IDirect3DDevice9*,
        const DWORD*,
        IDirect3DVertexShader9** shader)
    {
        if (!shader)
            return D3DERR_INVALIDCALL;
        *shader = reinterpret_cast<IDirect3DVertexShader9*>(&g_fakeVertexShader);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceCreatePixelShader(
        IDirect3DDevice9*,
        const DWORD* function,
        IDirect3DPixelShader9** shader)
    {
        if (!shader || !function)
            return D3DERR_INVALIDCALL;
        g_fakeLastPixelShaderVersion = function[0];
        InterlockedIncrement(&g_fakePixelShaderCreateCount);
        const LONG objectIndex =
            InterlockedIncrement(&g_fakePixelShaderObjectCount) - 1;
        if (objectIndex < 0 || objectIndex >= 4)
            return D3DERR_OUTOFVIDEOMEMORY;
        *shader = reinterpret_cast<IDirect3DPixelShader9*>(
            &g_fakePixelShaderObjects[objectIndex]);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceDrawPrimitive(
        IDirect3DDevice9*, D3DPRIMITIVETYPE, UINT, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceDrawIndexedPrimitive(
        IDirect3DDevice9*, D3DPRIMITIVETYPE, INT, UINT, UINT, UINT, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceDrawPrimitiveUP(
        IDirect3DDevice9*, D3DPRIMITIVETYPE, UINT, const void*, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceDrawIndexedPrimitiveUP(
        IDirect3DDevice9*, D3DPRIMITIVETYPE, UINT, UINT, UINT,
        const void*, D3DFORMAT, const void*, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetVertexShader(
        IDirect3DDevice9*,
        IDirect3DVertexShader9*)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetPixelShader(
        IDirect3DDevice9*,
        IDirect3DPixelShader9*)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceCreateVertexDeclaration(
        IDirect3DDevice9*,
        const D3DVERTEXELEMENT9*,
        IDirect3DVertexDeclaration9** declaration)
    {
        if (!declaration)
            return D3DERR_INVALIDCALL;
        *declaration = reinterpret_cast<IDirect3DVertexDeclaration9*>(&g_fakeVertexDeclaration);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetVertexDeclaration(
        IDirect3DDevice9*, IDirect3DVertexDeclaration9*)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetFVF(IDirect3DDevice9*, DWORD)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetStreamSource(
        IDirect3DDevice9*, UINT, IDirect3DVertexBuffer9*, UINT, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetStreamSourceFreq(IDirect3DDevice9*, UINT, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetIndices(IDirect3DDevice9*, IDirect3DIndexBuffer9*)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceCreateTexture(
        IDirect3DDevice9*,
        UINT,
        UINT,
        UINT,
        DWORD,
        D3DFORMAT,
        D3DPOOL,
        IDirect3DTexture9** texture,
        HANDLE*)
    {
        if (!texture)
            return D3DERR_INVALIDCALL;
        *texture = reinterpret_cast<IDirect3DTexture9*>(&g_fakeTexture);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetRenderState(
        IDirect3DDevice9*, D3DRENDERSTATETYPE, DWORD)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetTextureStageState(
        IDirect3DDevice9*, DWORD, D3DTEXTURESTAGESTATETYPE, DWORD)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetTexture(
        IDirect3DDevice9*, DWORD, IDirect3DBaseTexture9*)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetSamplerState(
        IDirect3DDevice9*, DWORD, D3DSAMPLERSTATETYPE, DWORD)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetVertexShaderConstantF(
        IDirect3DDevice9*, UINT, const float*, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetPixelShaderConstantF(
        IDirect3DDevice9*, UINT, const float*, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetVertexShaderConstantI(
        IDirect3DDevice9*, UINT, const int*, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetPixelShaderConstantI(
        IDirect3DDevice9*, UINT, const int*, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetVertexShaderConstantB(
        IDirect3DDevice9*, UINT, const BOOL*, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetPixelShaderConstantB(
        IDirect3DDevice9*, UINT, const BOOL*, UINT)
    {
        return D3D_OK;
    }

    HRESULT WINAPI FakeCreateDevice(
        IDirect3D9*,
        UINT,
        D3DDEVTYPE,
        HWND,
        DWORD,
        D3DPRESENT_PARAMETERS*,
        IDirect3DDevice9** device)
    {
        if (!device)
            return D3DERR_INVALIDCALL;
        *device = reinterpret_cast<IDirect3DDevice9*>(&g_fakeDevice);
        return D3D_OK;
    }

    IDirect3D9* WINAPI FakeDirect3DCreate9(UINT)
    {
        return reinterpret_cast<IDirect3D9*>(&g_fakeD3D9);
    }

    void InitializeFakeObjects()
    {
        for (unsigned i = 0; i < 17; ++i)
            g_fakeD3D9VTable[i] = reinterpret_cast<void*>(FakeUnused);
        g_fakeD3D9VTable[0] = reinterpret_cast<void*>(FakeQueryInterface);
        g_fakeD3D9VTable[1] = reinterpret_cast<void*>(FakeAddRef);
        g_fakeD3D9VTable[2] = reinterpret_cast<void*>(FakeRelease);
        g_fakeD3D9VTable[5] = reinterpret_cast<void*>(FakeGetAdapterIdentifier);
        g_fakeD3D9VTable[10] = reinterpret_cast<void*>(FakeCheckDeviceFormat);
        g_fakeD3D9VTable[12] = reinterpret_cast<void*>(FakeCheckDepthStencilMatch);
        g_fakeD3D9VTable[14] = reinterpret_cast<void*>(FakeGetDeviceCaps);
        g_fakeD3D9VTable[16] = reinterpret_cast<void*>(FakeCreateDevice);
        g_fakeD3D9.vtable = g_fakeD3D9VTable;

        for (unsigned i = 0; i < 119; ++i)
            g_fakeDeviceVTable[i] = reinterpret_cast<void*>(FakeUnused);
        g_fakeDeviceVTable[0] = reinterpret_cast<void*>(FakeQueryInterface);
        g_fakeDeviceVTable[1] = reinterpret_cast<void*>(FakeAddRef);
        g_fakeDeviceVTable[2] = reinterpret_cast<void*>(FakeRelease);
        g_fakeDeviceVTable[7] = reinterpret_cast<void*>(FakeDeviceGetDeviceCaps);
        g_fakeDeviceVTable[16] = reinterpret_cast<void*>(FakeDeviceReset);
        g_fakeDeviceVTable[17] = reinterpret_cast<void*>(FakeDevicePresent);
        g_fakeDeviceVTable[28] = reinterpret_cast<void*>(FakeDeviceCreateRenderTarget);
        g_fakeDeviceVTable[29] = reinterpret_cast<void*>(FakeDeviceCreateDepthStencilSurface);
        g_fakeDeviceVTable[37] = reinterpret_cast<void*>(FakeDeviceSetRenderTarget);
        g_fakeDeviceVTable[39] = reinterpret_cast<void*>(FakeDeviceSetDepthStencilSurface);
        g_fakeDeviceVTable[81] = reinterpret_cast<void*>(FakeDeviceDrawPrimitive);
        g_fakeDeviceVTable[82] = reinterpret_cast<void*>(FakeDeviceDrawIndexedPrimitive);
        g_fakeDeviceVTable[83] = reinterpret_cast<void*>(FakeDeviceDrawPrimitiveUP);
        g_fakeDeviceVTable[84] = reinterpret_cast<void*>(FakeDeviceDrawIndexedPrimitiveUP);
        g_fakeDeviceVTable[91] = reinterpret_cast<void*>(FakeDeviceCreateVertexShader);
        g_fakeDeviceVTable[92] = reinterpret_cast<void*>(FakeDeviceSetVertexShader);
        g_fakeDeviceVTable[106] = reinterpret_cast<void*>(FakeDeviceCreatePixelShader);
        g_fakeDeviceVTable[107] = reinterpret_cast<void*>(FakeDeviceSetPixelShader);
        g_fakeDeviceVTable[65] = reinterpret_cast<void*>(FakeDeviceSetTexture);
        g_fakeDeviceVTable[69] = reinterpret_cast<void*>(FakeDeviceSetSamplerState);
        g_fakeDeviceVTable[94] = reinterpret_cast<void*>(FakeDeviceSetVertexShaderConstantF);
        g_fakeDeviceVTable[96] = reinterpret_cast<void*>(FakeDeviceSetVertexShaderConstantI);
        g_fakeDeviceVTable[98] = reinterpret_cast<void*>(FakeDeviceSetVertexShaderConstantB);
        g_fakeDeviceVTable[109] = reinterpret_cast<void*>(FakeDeviceSetPixelShaderConstantF);
        g_fakeDeviceVTable[111] = reinterpret_cast<void*>(FakeDeviceSetPixelShaderConstantI);
        g_fakeDeviceVTable[113] = reinterpret_cast<void*>(FakeDeviceSetPixelShaderConstantB);
        g_fakeDeviceVTable[23] = reinterpret_cast<void*>(FakeDeviceCreateTexture);
        g_fakeDeviceVTable[57] = reinterpret_cast<void*>(FakeDeviceSetRenderState);
        g_fakeDeviceVTable[67] = reinterpret_cast<void*>(FakeDeviceSetTextureStageState);
        g_fakeDeviceVTable[86] = reinterpret_cast<void*>(FakeDeviceCreateVertexDeclaration);
        g_fakeDeviceVTable[87] = reinterpret_cast<void*>(FakeDeviceSetVertexDeclaration);
        g_fakeDeviceVTable[89] = reinterpret_cast<void*>(FakeDeviceSetFVF);
        g_fakeDeviceVTable[100] = reinterpret_cast<void*>(FakeDeviceSetStreamSource);
        g_fakeDeviceVTable[102] = reinterpret_cast<void*>(FakeDeviceSetStreamSourceFreq);
        g_fakeDeviceVTable[104] = reinterpret_cast<void*>(FakeDeviceSetIndices);
        g_fakeDevice.vtable = g_fakeDeviceVTable;

        g_fakeShaderVTable[0] = reinterpret_cast<void*>(FakeQueryInterface);
        g_fakeShaderVTable[1] = reinterpret_cast<void*>(FakeAddRef);
        g_fakeShaderVTable[2] = reinterpret_cast<void*>(FakeRelease);
        g_fakeVertexShader.vtable = g_fakeShaderVTable;
        for (unsigned i = 0; i < 4; ++i)
            g_fakePixelShaderObjects[i].vtable = g_fakeShaderVTable;

        g_fakeTextureVTable[0] = reinterpret_cast<void*>(FakeQueryInterface);
        g_fakeTextureVTable[1] = reinterpret_cast<void*>(FakeAddRef);
        g_fakeTextureVTable[2] = reinterpret_cast<void*>(FakeRelease);
        g_fakeTexture.vtable = g_fakeTextureVTable;
        g_fakeVertexDeclaration.vtable = g_fakeShaderVTable;
        g_fakeVertexBuffer.vtable = g_fakeTextureVTable;
        g_fakeIndexBuffer.vtable = g_fakeTextureVTable;
    }

    bool PatchImportToFakeCreate9()
    {
        HMODULE exe = GetModuleHandleW(NULL);
        if (!exe)
            return false;

        BYTE* base = reinterpret_cast<BYTE*>(exe);
        IMAGE_DOS_HEADER* dos = reinterpret_cast<IMAGE_DOS_HEADER*>(base);
        if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0)
            return false;

        IMAGE_NT_HEADERS32* nt =
            reinterpret_cast<IMAGE_NT_HEADERS32*>(base + dos->e_lfanew);
        if (nt->Signature != IMAGE_NT_SIGNATURE ||
            nt->FileHeader.Machine != IMAGE_FILE_MACHINE_I386)
            return false;

        const IMAGE_DATA_DIRECTORY directory =
            nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
        if (!directory.VirtualAddress)
            return false;

        IMAGE_IMPORT_DESCRIPTOR* descriptor =
            reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(base + directory.VirtualAddress);
        for (; descriptor->Name; ++descriptor)
        {
            const char* moduleName =
                reinterpret_cast<const char*>(base + descriptor->Name);
            if (_stricmp(moduleName, "d3d9.dll") != 0 ||
                !descriptor->OriginalFirstThunk)
                continue;

            IMAGE_THUNK_DATA32* names =
                reinterpret_cast<IMAGE_THUNK_DATA32*>(base + descriptor->OriginalFirstThunk);
            IMAGE_THUNK_DATA32* addresses =
                reinterpret_cast<IMAGE_THUNK_DATA32*>(base + descriptor->FirstThunk);

            for (; names->u1.AddressOfData; ++names, ++addresses)
            {
                if (IMAGE_SNAP_BY_ORDINAL32(names->u1.Ordinal))
                    continue;

                IMAGE_IMPORT_BY_NAME* importName =
                    reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(base + names->u1.AddressOfData);
                if (strcmp(reinterpret_cast<const char*>(importName->Name),
                    "Direct3DCreate9") != 0)
                    continue;

                DWORD oldProtection = 0;
                if (!VirtualProtect(
                    &addresses->u1.Function,
                    sizeof(addresses->u1.Function),
                    PAGE_READWRITE,
                    &oldProtection))
                    return false;

                InterlockedExchange(
                    reinterpret_cast<volatile LONG*>(&addresses->u1.Function),
                    static_cast<LONG>(
                        reinterpret_cast<ULONG_PTR>(FakeDirect3DCreate9)));

                DWORD ignored = 0;
                VirtualProtect(
                    &addresses->u1.Function,
                    sizeof(addresses->u1.Function),
                    oldProtection,
                    &ignored);
                FlushInstructionCache(
                    GetCurrentProcess(),
                    &addresses->u1.Function,
                    sizeof(addresses->u1.Function));
                return true;
            }
        }
        return false;
    }
}

int main()
{
    SetUnhandledExceptionFilter(SmokeUnhandledExceptionFilter);
    InitializeFakeObjects();
    BuildSyntheticPs3Shader();

    // First touch the real export so the executable has a normal d3d9.dll
    // import and its IAT points to the system export before we replace it.
    IDirect3D9* realD3D = Direct3DCreate9(D3D_SDK_VERSION);
    if (!realD3D)
        return Fail("Real Direct3DCreate9 export returned NULL");
    realD3D->Release();

    if (!PatchImportToFakeCreate9())
        return Fail("Could not patch the synthetic host IAT to its fake D3D9 factory");

    const wchar_t* iniPath = L"build\\bin\\IVLegacy.ini";
    WritePrivateProfileStringW(
        L"General", L"EnableD3D9Telemetry", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"StrictGTAIV100", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"CaptureShaderBytecode", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"CaptureMaxFiles", L"16", iniPath);
    WritePrivateProfileStringW(
        L"General", L"CaptureDrawTelemetry", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"CaptureDrawMaxCalls", L"8", iniPath);
    WritePrivateProfileStringW(
        L"General", L"CaptureShaderConstants", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"CaptureShaderConstantMaxRecords", L"16", iniPath);
    WritePrivateProfileStringW(
        L"General", L"EnableShaderFallbacks", L"1", iniPath);

    const wchar_t* fallbackFolder = L"build\\bin\\IVLegacyFallbacks";
    if (!CreateDirectoryW(fallbackFolder, NULL) &&
        GetLastError() != ERROR_ALREADY_EXISTS)
    {
        return Fail("Could not create synthetic shader fallback directory");
    }

    if (!CopyFileW(
        L"build\\out\\basic_ps20.pso",
        L"build\\bin\\IVLegacyFallbacks\\smoke.ps20.pso",
        FALSE))
    {
        return Fail("Could not stage synthetic PS2 fallback bytecode");
    }

    const unsigned __int64 syntheticHash = HashShaderBytes(
        reinterpret_cast<const BYTE*>(g_syntheticPs3PixelShader),
        sizeof(g_syntheticPs3PixelShader));
    wchar_t syntheticHashKey[32] = {};
    _snwprintf_s(
        syntheticHashKey,
        _countof(syntheticHashKey),
        _TRUNCATE,
        L"%016llX",
        syntheticHash);
    const wchar_t* fallbackIniPath = L"build\\bin\\IVLegacyShaderFallbacks.ini";
    DeleteFileW(fallbackIniPath);
    if (!WritePrivateProfileStringW(
        L"ShaderFallbacks",
        syntheticHashKey,
        L"IVLegacyFallbacks\\smoke.ps20.pso",
        fallbackIniPath))
    {
        return Fail("Could not write synthetic hash-to-PS2 fallback mapping");
    }

    DeleteFileW(L"build\\bin\\IVLegacy.log");

    SmokeMark("before-LoadLibrary");
    HMODULE asi = LoadLibraryW(L"build\\bin\\IVLegacyASI.asi");
    SmokeMark("after-LoadLibrary");
    if (!asi)
        return Fail("LoadLibrary failed for IVLegacyASI.asi");

    FARPROC initializeAddress = GetProcAddress(asi, "InitializeASI");
    if (!initializeAddress)
        return Fail("ASI does not export the undecorated InitializeASI entry point");

    typedef void (*InitializeASIFn)(void);
    InitializeASIFn initializeASI =
        reinterpret_cast<InitializeASIFn>(initializeAddress);
    SmokeMark("before-InitializeASI");
    initializeASI();
    SmokeMark("after-InitializeASI");

    if (!WaitForLog("D3D9_IAT_HOOK_INSTALLED", 10000))
        return Fail("ASI bootstrap did not install the Direct3DCreate9 IAT hook");

    SmokeMark("before-hooked-Direct3DCreate9");
    IDirect3D9* d3d = Direct3DCreate9(D3D_SDK_VERSION);
    SmokeMark("after-hooked-Direct3DCreate9");
    if (!d3d)
        return Fail("Hooked Direct3DCreate9 returned NULL");

    D3DADAPTER_IDENTIFIER9 identifier = {};
    const HRESULT identifierHr = d3d->GetAdapterIdentifier(0, 0, &identifier);

    D3DCAPS9 caps = {};
    const HRESULT capsHr = d3d->GetDeviceCaps(0, D3DDEVTYPE_HAL, &caps);
    const HRESULT formatHr = d3d->CheckDeviceFormat(
        0, D3DDEVTYPE_HAL, D3DFMT_X8R8G8B8,
        D3DUSAGE_RENDERTARGET, D3DRTYPE_TEXTURE, D3DFMT_A8R8G8B8);
    const HRESULT depthHr = d3d->CheckDepthStencilMatch(
        0, D3DDEVTYPE_HAL, D3DFMT_X8R8G8B8,
        D3DFMT_A8R8G8B8, D3DFMT_D24S8);

    D3DPRESENT_PARAMETERS parameters = {};
    parameters.BackBufferWidth = 64;
    parameters.BackBufferHeight = 64;
    parameters.BackBufferFormat = D3DFMT_X8R8G8B8;
    parameters.BackBufferCount = 1;
    parameters.SwapEffect = D3DSWAPEFFECT_DISCARD;
    parameters.Windowed = TRUE;
    parameters.EnableAutoDepthStencil = FALSE;
    parameters.PresentationInterval = D3DPRESENT_INTERVAL_IMMEDIATE;

    IDirect3DDevice9* device = NULL;
    SmokeMark("before-synthetic-CreateDevice");
    const HRESULT createDeviceHr = d3d->CreateDevice(
        0,
        D3DDEVTYPE_HAL,
        NULL,
        D3DCREATE_SOFTWARE_VERTEXPROCESSING,
        &parameters,
        &device);
    SmokeMark("after-synthetic-CreateDevice");

    if (FAILED(createDeviceHr) || !device)
        return Fail("Synthetic IDirect3D9::CreateDevice hook returned failure");

    D3DCAPS9 deviceCaps = {};
    const HRESULT deviceCapsHr = device->GetDeviceCaps(&deviceCaps);

    HRESULT resetHr = device->Reset(&parameters);
    HRESULT presentHr = device->Present(NULL, NULL, NULL, NULL);

    IDirect3DSurface9* renderTarget = NULL;
    const HRESULT renderTargetHr = device->CreateRenderTarget(
        32, 32, D3DFMT_A8R8G8B8,
        D3DMULTISAMPLE_NONE, 0, FALSE, &renderTarget, NULL);

    IDirect3DSurface9* depthSurface = NULL;
    const HRESULT depthSurfaceHr = device->CreateDepthStencilSurface(
        32, 32, D3DFMT_D24S8,
        D3DMULTISAMPLE_NONE, 0, TRUE, &depthSurface, NULL);

    const HRESULT setRenderTargetHr = device->SetRenderTarget(0, NULL);
    const HRESULT setDepthSurfaceHr = device->SetDepthStencilSurface(NULL);

    BYTE* vertexBytecode = NULL;
    BYTE* pixelBytecode = NULL;
    DWORD vertexBytecodeSize = 0;
    DWORD pixelBytecodeSize = 0;

    HANDLE vertexFile = CreateFileW(
        L"build\\out\\basic_vs20.vso",
        GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (vertexFile != INVALID_HANDLE_VALUE)
    {
        LARGE_INTEGER fileSize = {};
        if (GetFileSizeEx(vertexFile, &fileSize) &&
            fileSize.QuadPart > 0 &&
            fileSize.QuadPart <= 1024 * 1024 &&
            (fileSize.QuadPart % sizeof(DWORD)) == 0)
        {
            vertexBytecodeSize = static_cast<DWORD>(fileSize.QuadPart);
            vertexBytecode = static_cast<BYTE*>(
                HeapAlloc(GetProcessHeap(), 0, vertexBytecodeSize));
            DWORD read = 0;
            if (!vertexBytecode ||
                !ReadFile(vertexFile, vertexBytecode, vertexBytecodeSize, &read, NULL) ||
                read != vertexBytecodeSize)
            {
                if (vertexBytecode)
                    HeapFree(GetProcessHeap(), 0, vertexBytecode);
                vertexBytecode = NULL;
            }
        }
        CloseHandle(vertexFile);
    }

    HANDLE pixelFile = CreateFileW(
        L"build\\out\\basic_ps20.pso",
        GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (pixelFile != INVALID_HANDLE_VALUE)
    {
        LARGE_INTEGER fileSize = {};
        if (GetFileSizeEx(pixelFile, &fileSize) &&
            fileSize.QuadPart > 0 &&
            fileSize.QuadPart <= 1024 * 1024 &&
            (fileSize.QuadPart % sizeof(DWORD)) == 0)
        {
            pixelBytecodeSize = static_cast<DWORD>(fileSize.QuadPart);
            pixelBytecode = static_cast<BYTE*>(
                HeapAlloc(GetProcessHeap(), 0, pixelBytecodeSize));
            DWORD read = 0;
            if (!pixelBytecode ||
                !ReadFile(pixelFile, pixelBytecode, pixelBytecodeSize, &read, NULL) ||
                read != pixelBytecodeSize)
            {
                if (pixelBytecode)
                    HeapFree(GetProcessHeap(), 0, pixelBytecode);
                pixelBytecode = NULL;
            }
        }
        CloseHandle(pixelFile);
    }

    IDirect3DVertexShader9* vertexShader = NULL;
    IDirect3DPixelShader9* fallbackPixelShader = NULL;
    IDirect3DPixelShader9* unmappedPixelShader = NULL;
    IDirect3DPixelShader9* pixelShader = NULL;
    HRESULT vertexShaderHr = D3DERR_INVALIDCALL;
    HRESULT pixelShaderHr = D3DERR_INVALIDCALL;
    HRESULT fallbackShaderHr = D3DERR_INVALIDCALL;
    HRESULT unmappedShaderHr = D3DERR_INVALIDCALL;
    DWORD mappedShaderVersion = 0;
    DWORD unmappedShaderVersion = 0;

    if (vertexBytecode)
        vertexShaderHr = device->CreateVertexShader(
            reinterpret_cast<const DWORD*>(vertexBytecode), &vertexShader);

    fallbackShaderHr = device->CreatePixelShader(
        g_syntheticPs3PixelShader, &fallbackPixelShader);
    mappedShaderVersion = g_fakeLastPixelShaderVersion;

    unmappedShaderHr = device->CreatePixelShader(
        g_syntheticPs3PixelShaderAlt, &unmappedPixelShader);
    unmappedShaderVersion = g_fakeLastPixelShaderVersion;

    if (pixelBytecode)
        pixelShaderHr = device->CreatePixelShader(
            reinterpret_cast<const DWORD*>(pixelBytecode), &pixelShader);

    const HRESULT setVertexShaderHr = device->SetVertexShader(vertexShader);
    // Draw with the actual PS2 replacement object to test end-to-end correlation.
    const HRESULT setPixelShaderHr = device->SetPixelShader(fallbackPixelShader);

    const float vertexConstants[4] = { 1.0f, 2.0f, 3.0f, 4.0f };
    const float pixelConstants[4] = { 0.25f, 0.5f, 0.75f, 1.0f };
    const int vertexIntegerConstants[4] = { 1, -2, 3, -4 };
    const int pixelIntegerConstants[4] = { -5, 6, -7, 8 };
    const BOOL vertexBooleanConstants[2] = { FALSE, TRUE };
    const BOOL pixelBooleanConstants[2] = { TRUE, FALSE };
    IDirect3DTexture9* fakeTexture = NULL;
    const HRESULT createTextureHr = device->CreateTexture(
        64, 32, 1, 0, D3DFMT_A8R8G8B8, D3DPOOL_MANAGED,
        &fakeTexture, NULL);
    const HRESULT setTextureHr = device->SetTexture(
        0, reinterpret_cast<IDirect3DBaseTexture9*>(fakeTexture));
    const HRESULT setSamplerStateHr = device->SetSamplerState(
        0, D3DSAMP_MINFILTER, D3DTEXF_POINT);
    const HRESULT setRenderStateHr = device->SetRenderState(
        D3DRS_ALPHABLENDENABLE, TRUE);
    const HRESULT setTextureStageStateHr = device->SetTextureStageState(
        0, D3DTSS_COLOROP, D3DTOP_MODULATE);
    const HRESULT setVertexConstantsHr = device->SetVertexShaderConstantF(
        4, vertexConstants, 1);
    const HRESULT setPixelConstantsHr = device->SetPixelShaderConstantF(
        7, pixelConstants, 1);
    const HRESULT setVertexIntegerConstantsHr = device->SetVertexShaderConstantI(
        2, vertexIntegerConstants, 1);
    const HRESULT setPixelIntegerConstantsHr = device->SetPixelShaderConstantI(
        1, pixelIntegerConstants, 1);
    const HRESULT setVertexBooleanConstantsHr = device->SetVertexShaderConstantB(
        4, vertexBooleanConstants, 2);
    const HRESULT setPixelBooleanConstantsHr = device->SetPixelShaderConstantB(
        5, pixelBooleanConstants, 2);

    const HRESULT drawPrimitiveHr = device->DrawPrimitive(
        D3DPT_TRIANGLELIST, 0, 1);
    const HRESULT drawIndexedPrimitiveHr = device->DrawIndexedPrimitive(
        D3DPT_TRIANGLELIST, 0, 0, 3, 0, 1);
    const HRESULT drawPrimitiveUPHr = device->DrawPrimitiveUP(
        D3DPT_TRIANGLELIST, 1, NULL, sizeof(float) * 3);
    const HRESULT drawIndexedPrimitiveUPHr = device->DrawIndexedPrimitiveUP(
        D3DPT_TRIANGLELIST, 0, 3, 1, NULL, D3DFMT_INDEX16,
        NULL, sizeof(float) * 3);

    if (vertexBytecode)
        HeapFree(GetProcessHeap(), 0, vertexBytecode);
    if (pixelBytecode)
        HeapFree(GetProcessHeap(), 0, pixelBytecode);

    if (renderTarget)
        renderTarget->Release();
    if (depthSurface)
        depthSurface->Release();
    if (vertexShader)
        vertexShader->Release();
    if (pixelShader)
        pixelShader->Release();
    if (unmappedPixelShader)
        unmappedPixelShader->Release();
    if (fallbackPixelShader)
        fallbackPixelShader->Release();
    if (fakeTexture)
        fakeTexture->Release();
    device->Release();
    d3d->Release();

    if (!WaitForLog("DIRECT3DCREATE9", 5000))
        return Fail("Direct3DCreate9 wrapper was not called");
    if (!HasText("D3D9_ADAPTER"))
        return Fail("IDirect3D9::GetAdapterIdentifier hook was not observed");
    if (!HasText("D3D9_GET_DEVICE_CAPS"))
        return Fail("IDirect3D9::GetDeviceCaps hook was not observed");
    if (!HasText("D3D9_CHECK_DEVICE_FORMAT"))
        return Fail("IDirect3D9::CheckDeviceFormat hook was not observed");
    if (!HasText("D3D9_CHECK_DEPTH_MATCH"))
        return Fail("IDirect3D9::CheckDepthStencilMatch hook was not observed");
    if (!HasText("D3D9_DEVICE_HOOK_BEGIN") ||
        !HasText("D3D9_DEVICE_VTABLE_COPIED") ||
        !HasText("D3D9_DEVICE_HOOK_INSTALLED"))
        return Fail("IDirect3DDevice9 vtable hook was not installed");

    if (!HasText("DEVICE_GET_DEVICE_CAPS"))
        return Fail("IDirect3DDevice9::GetDeviceCaps hook was not observed");
    if (!HasText("DEVICE_RESET_REQUEST") || !HasText("DEVICE_RESET_RESULT"))
        return Fail("IDirect3DDevice9::Reset hook was not observed");
    if (!HasText("CREATE_RENDER_TARGET") || !HasText("CREATE_DEPTH_STENCIL_SURFACE"))
        return Fail("Device render/depth surface creation hooks were not observed");
    if (!HasText("CREATE_VERTEX_SHADER") || !HasText("CREATE_PIXEL_SHADER"))
        return Fail("Device shader creation hooks were not observed");
    if (!HasText("SHADER_FALLBACKS_ENABLED") ||
        !HasText("SHADER_FALLBACK_APPLIED"))
        return Fail("Configured PS2 fallback was not applied to the matching PS3 shader");
    if (!HasText("SHADER_FALLBACK_OBJECT_MAP") ||
        !HasText("target_profile=ps_2_0") ||
        !HasText("SHADER_OBJECT_CREATED stage=PS object=") ||
        !HasText("profile=PS_2_0"))
        return Fail("Fallback shader object was not correlated with its actual PS2 bytecode");
    if (!HasText("SHADER_FALLBACK_NOT_MAPPED"))
        return Fail("Unmapped PS3 shader did not pass through unchanged");
    if (FAILED(fallbackShaderHr) || FAILED(unmappedShaderHr) ||
        mappedShaderVersion != 0xFFFF0200UL ||
        unmappedShaderVersion != 0xFFFF0300UL)
        return Fail("Hash-mapped shader substitution did not preserve fallback/pass-through profiles");
    if (!HasText("SET_VERTEX_SHADER") || !HasText("SET_PIXEL_SHADER"))
        return Fail("Device shader binding hooks were not observed");
    if (!HasText("SHADER_OBJECT_CREATED stage=VS") ||
        !HasText("SHADER_OBJECT_CREATED stage=PS"))
        return Fail("Shader object-to-bytecode hash correlation was not logged");
    if (!HasText("DRAW_TELEMETRY_ENABLED") ||
        !HasText("frame=1") ||
        !HasText("kind=DrawPrimitive") ||
        !HasText("kind=DrawIndexedPrimitive") ||
        !HasText("kind=DrawPrimitiveUP") ||
        !HasText("kind=DrawIndexedPrimitiveUP"))
        return Fail("One or more D3D9 draw telemetry hooks or frame tags were not observed");
    if (!HasText("TEXTURE_OBJECT_CREATED type=2D") ||
        !HasText("SET_TEXTURE") || !HasText("SET_SAMPLER_STATE"))
        return Fail("D3D9 texture creation, binding or sampler-state hooks were not observed");
    if (!HasText("SET_RENDER_STATE") ||
        !HasText("SET_TEXTURE_STAGE_STATE") ||
        !HasText("render_state_count=1") ||
        !HasText("texture_stage_count=1"))
        return Fail("D3D9 render-state or texture-stage snapshot hooks were not observed");
    if (!HasText("SHADER_CONSTANT_CAPTURE_ENABLED") ||
        !HasText("SHADER_CONSTANT_CAPTURED stage=VS kind=F") ||
        !HasText("SHADER_CONSTANT_CAPTURED stage=PS kind=F") ||
        !HasText("SHADER_CONSTANT_CAPTURED stage=VS kind=I") ||
        !HasText("SHADER_CONSTANT_CAPTURED stage=PS kind=I") ||
        !HasText("SHADER_CONSTANT_CAPTURED stage=VS kind=B") ||
        !HasText("SHADER_CONSTANT_CAPTURED stage=PS kind=B"))
        return Fail("Float/integer/boolean VS/PS constant sidecar capture was not observed");
    if (!HasText("SHADER_CAPTURE_ENABLED") ||
        !HasText("SHADER_CAPTURED stage=VS") ||
        !HasText("SHADER_CAPTURED stage=PS"))
    {
        return Fail("Opt-in bounded SM2 shader bytecode capture was not verified");
    }

    WIN32_FIND_DATAW findData = {};
    HANDLE find = FindFirstFileW(
        L"build\\bin\\IVLegacyCaptures\\*.bin", &findData);
    if (find == INVALID_HANDLE_VALUE)
        return Fail("Shader capture output directory contains no bytecode files");

    unsigned captureFiles = 0;
    do
    {
        if ((findData.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) == 0)
            ++captureFiles;
    } while (FindNextFileW(find, &findData));
    FindClose(find);

    if (captureFiles < 2 || captureFiles > 16)
        return Fail("Shader capture file count is outside the configured bound");

    WIN32_FIND_DATAW constantFindData = {};
    HANDLE constantFind = FindFirstFileW(
        L"build\\bin\\IVLegacyConstants\\*.bin", &constantFindData);
    if (constantFind == INVALID_HANDLE_VALUE)
        return Fail("Shader constant sidecar directory contains no binary records");
    unsigned constantFiles = 0;
    do
    {
        if ((constantFindData.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) == 0)
            ++constantFiles;
    } while (FindNextFileW(constantFind, &constantFindData));
    FindClose(constantFind);
    if (constantFiles != 6)
        return Fail("Expected six bounded float/integer/boolean shader constant sidecar records");

    std::printf("PASS: synthetic D3D9 interface/device hooks, shader capture and constant telemetry executed.\n");
    std::printf("Adapter: %s; vendor=0x%04lX device=0x%04lX\n",
        identifier.Description,
        static_cast<unsigned long>(identifier.VendorId),
        static_cast<unsigned long>(identifier.DeviceId));
    std::printf("CreateDevice HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(createDeviceHr));
    std::printf("Device caps HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(deviceCapsHr));
    std::printf("Reset HRESULT: 0x%08lX; Present HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(resetHr),
        static_cast<unsigned long>(presentHr));
    std::printf("CreateRT HRESULT: 0x%08lX; CreateDepth HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(renderTargetHr),
        static_cast<unsigned long>(depthSurfaceHr));
    std::printf("SetRT HRESULT: 0x%08lX; SetDepth HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(setRenderTargetHr),
        static_cast<unsigned long>(setDepthSurfaceHr));
    std::printf("CreateVS HRESULT: 0x%08lX; CreatePS HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(vertexShaderHr),
        static_cast<unsigned long>(pixelShaderHr));
    std::printf("DrawPrimitive HRESULT: 0x%08lX; DrawIndexedPrimitive HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(drawPrimitiveHr),
        static_cast<unsigned long>(drawIndexedPrimitiveHr));
    std::printf("DrawPrimitiveUP HRESULT: 0x%08lX; DrawIndexedPrimitiveUP HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(drawPrimitiveUPHr),
        static_cast<unsigned long>(drawIndexedPrimitiveUPHr));
    std::printf("Captured shader files: %u\n", captureFiles);
    std::printf("Captured constant records: %u\n", constantFiles);

    (void)asi;
    return 0;
}
