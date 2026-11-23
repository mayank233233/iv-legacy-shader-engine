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
    DWORD g_fakeLastVertexShaderVersion = 0;
    volatile LONG g_fakePixelShaderCreateCount = 0;
    volatile LONG g_fakeVertexShaderCreateCount = 0;
    volatile LONG g_fakePixelShaderObjectCount = 0;
    volatile LONG g_fakeGetRenderTargetCount = 0;
    volatile LONG g_fakeGetDepthStencilSurfaceCount = 0;
    volatile LONG g_fakeSetRenderStateCalls = 0;
    volatile LONG g_fakeSetTextureStageStateCalls = 0;
    volatile LONG g_fakeSetSamplerStateCalls = 0;
    volatile LONG g_fakeBeginStateBlockCalls = 0;
    volatile LONG g_fakeCreateStateBlockCalls = 0;
    volatile LONG g_fakeEndStateBlockCalls = 0;
    volatile LONG g_fakeGetRenderStateCalls = 0;
    volatile LONG g_fakeSetViewportCalls = 0;
    volatile LONG g_fakeSetVertexFloatConstantsCalls = 0;
    volatile LONG g_fakeSetPixelFloatConstantsCalls = 0;
    volatile LONG g_fakeSetVertexIntegerConstantsCalls = 0;
    volatile LONG g_fakeSetPixelIntegerConstantsCalls = 0;
    volatile LONG g_fakeSetVertexBooleanConstantsCalls = 0;
    volatile LONG g_fakeSetPixelBooleanConstantsCalls = 0;
    volatile LONG g_fakeSetTextureCalls = 0;
    volatile LONG g_fakeSetStreamSourceCalls = 0;
    volatile LONG g_fakeSetStreamSourceFreqCalls = 0;
    volatile LONG g_fakeSetIndicesCalls = 0;
    volatile LONG g_fakeSetVertexShaderCalls = 0;
    volatile LONG g_fakeSetPixelShaderCalls = 0;
    volatile LONG g_fakeSetVertexDeclarationCalls = 0;
    volatile LONG g_fakeSetFVFCalls = 0;
    DWORD g_syntheticPs3PixelShader[18] = {};
    DWORD g_syntheticPs3PixelShaderAlt[18] = {};
    DWORD g_syntheticVs3VertexShader[11] = {};

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

    void BuildSyntheticVs3Shader()
    {
        DWORD index = 0;
        g_syntheticVs3VertexShader[index++] = 0xFFFE0300UL;
        // dcl_position v0
        g_syntheticVs3VertexShader[index++] = (2UL << 24) | 31UL;
        g_syntheticVs3VertexShader[index++] = 0x80000000UL;
        g_syntheticVs3VertexShader[index++] = MakeShaderRegisterToken(1, 0);
        // dcl_position o0
        g_syntheticVs3VertexShader[index++] = (2UL << 24) | 31UL;
        g_syntheticVs3VertexShader[index++] = 0x80000000UL;
        g_syntheticVs3VertexShader[index++] = MakeShaderRegisterToken(6, 0);
        // mov o0, v0
        g_syntheticVs3VertexShader[index++] = (2UL << 24) | 1UL;
        g_syntheticVs3VertexShader[index++] = MakeShaderRegisterToken(6, 0);
        g_syntheticVs3VertexShader[index++] = MakeShaderSourceToken(1, 0);
        g_syntheticVs3VertexShader[index++] = 0x0000FFFFUL;

        if (index != _countof(g_syntheticVs3VertexShader))
            std::abort();
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
        caps->DevCaps = D3DDEVCAPS_HWTRANSFORMANDLIGHT;
        caps->VertexProcessingCaps = D3DVTXPCAPS_TEXGEN;
        caps->MaxStreams = 16;
        caps->MaxStreamStride = 255;
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

    HRESULT WINAPI FakeDeviceSetViewport(
        IDirect3DDevice9*,
        const D3DVIEWPORT9* viewport)
    {
        if (!viewport ||
            (viewport->Width != 64 && viewport->Width != 63) ||
            viewport->Height != 48)
            return D3DERR_INVALIDCALL;
        InterlockedIncrement(&g_fakeSetViewportCalls);
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

    HRESULT WINAPI FakeDeviceGetRenderTarget(
        IDirect3DDevice9*,
        DWORD,
        IDirect3DSurface9** surface)
    {
        InterlockedIncrement(&g_fakeGetRenderTargetCount);
        if (!surface)
            return D3DERR_INVALIDCALL;
        *surface = NULL;
        return D3DERR_NOTFOUND;
    }

    HRESULT WINAPI FakeDeviceGetDepthStencilSurface(
        IDirect3DDevice9*,
        IDirect3DSurface9** surface)
    {
        InterlockedIncrement(&g_fakeGetDepthStencilSurfaceCount);
        if (!surface)
            return D3DERR_INVALIDCALL;
        *surface = NULL;
        return D3DERR_NOTFOUND;
    }

    HRESULT WINAPI FakeDeviceCreateVertexShader(
        IDirect3DDevice9*,
        const DWORD* function,
        IDirect3DVertexShader9** shader)
    {
        if (!shader || !function)
            return D3DERR_INVALIDCALL;
        g_fakeLastVertexShaderVersion = function[0];
        InterlockedIncrement(&g_fakeVertexShaderCreateCount);
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
        InterlockedIncrement(&g_fakeSetVertexShaderCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetPixelShader(
        IDirect3DDevice9*,
        IDirect3DPixelShader9*)
    {
        InterlockedIncrement(&g_fakeSetPixelShaderCalls);
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
        InterlockedIncrement(&g_fakeSetVertexDeclarationCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetFVF(IDirect3DDevice9*, DWORD)
    {
        InterlockedIncrement(&g_fakeSetFVFCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetStreamSource(
        IDirect3DDevice9*, UINT, IDirect3DVertexBuffer9*, UINT, UINT)
    {
        InterlockedIncrement(&g_fakeSetStreamSourceCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetStreamSourceFreq(IDirect3DDevice9*, UINT, UINT)
    {
        InterlockedIncrement(&g_fakeSetStreamSourceFreqCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetIndices(IDirect3DDevice9*, IDirect3DIndexBuffer9*)
    {
        InterlockedIncrement(&g_fakeSetIndicesCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceCreateVertexBuffer(
        IDirect3DDevice9*,
        UINT,
        DWORD,
        DWORD,
        D3DPOOL,
        IDirect3DVertexBuffer9** buffer,
        HANDLE*)
    {
        if (!buffer)
            return D3DERR_INVALIDCALL;
        *buffer = reinterpret_cast<IDirect3DVertexBuffer9*>(&g_fakeVertexBuffer);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceCreateIndexBuffer(
        IDirect3DDevice9*,
        UINT,
        DWORD,
        D3DFORMAT,
        D3DPOOL,
        IDirect3DIndexBuffer9** buffer,
        HANDLE*)
    {
        if (!buffer)
            return D3DERR_INVALIDCALL;
        *buffer = reinterpret_cast<IDirect3DIndexBuffer9*>(&g_fakeIndexBuffer);
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
        InterlockedIncrement(&g_fakeSetRenderStateCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceGetRenderState(
        IDirect3DDevice9*, D3DRENDERSTATETYPE, DWORD* value)
    {
        if (!value)
            return D3DERR_INVALIDCALL;
        InterlockedIncrement(&g_fakeGetRenderStateCalls);
        *value = 0;
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetTextureStageState(
        IDirect3DDevice9*, DWORD, D3DTEXTURESTAGESTATETYPE, DWORD)
    {
        InterlockedIncrement(&g_fakeSetTextureStageStateCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetTexture(
        IDirect3DDevice9*, DWORD, IDirect3DBaseTexture9*)
    {
        InterlockedIncrement(&g_fakeSetTextureCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetSamplerState(
        IDirect3DDevice9*, DWORD, D3DSAMPLERSTATETYPE, DWORD)
    {
        InterlockedIncrement(&g_fakeSetSamplerStateCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceCreateStateBlock(
        IDirect3DDevice9*, D3DSTATEBLOCKTYPE, IDirect3DStateBlock9** stateBlock)
    {
        InterlockedIncrement(&g_fakeCreateStateBlockCalls);
        if (stateBlock)
            *stateBlock = NULL;
        return D3DERR_INVALIDCALL;
    }

    HRESULT WINAPI FakeDeviceBeginStateBlock(IDirect3DDevice9*)
    {
        InterlockedIncrement(&g_fakeBeginStateBlockCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceEndStateBlock(
        IDirect3DDevice9*, IDirect3DStateBlock9** stateBlock)
    {
        InterlockedIncrement(&g_fakeEndStateBlockCalls);
        if (stateBlock)
            *stateBlock = NULL;
        return D3DERR_INVALIDCALL;
    }

    HRESULT WINAPI FakeDeviceSetVertexShaderConstantF(
        IDirect3DDevice9*, UINT, const float*, UINT)
    {
        InterlockedIncrement(&g_fakeSetVertexFloatConstantsCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetPixelShaderConstantF(
        IDirect3DDevice9*, UINT, const float*, UINT)
    {
        InterlockedIncrement(&g_fakeSetPixelFloatConstantsCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetVertexShaderConstantI(
        IDirect3DDevice9*, UINT, const int*, UINT)
    {
        InterlockedIncrement(&g_fakeSetVertexIntegerConstantsCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetPixelShaderConstantI(
        IDirect3DDevice9*, UINT, const int*, UINT)
    {
        InterlockedIncrement(&g_fakeSetPixelIntegerConstantsCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetVertexShaderConstantB(
        IDirect3DDevice9*, UINT, const BOOL*, UINT)
    {
        InterlockedIncrement(&g_fakeSetVertexBooleanConstantsCalls);
        return D3D_OK;
    }

    HRESULT WINAPI FakeDeviceSetPixelShaderConstantB(
        IDirect3DDevice9*, UINT, const BOOL*, UINT)
    {
        InterlockedIncrement(&g_fakeSetPixelBooleanConstantsCalls);
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
        g_fakeDeviceVTable[47] = reinterpret_cast<void*>(FakeDeviceSetViewport);
        g_fakeDeviceVTable[38] = reinterpret_cast<void*>(FakeDeviceGetRenderTarget);
        g_fakeDeviceVTable[39] = reinterpret_cast<void*>(FakeDeviceSetDepthStencilSurface);
        g_fakeDeviceVTable[40] = reinterpret_cast<void*>(FakeDeviceGetDepthStencilSurface);
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
        g_fakeDeviceVTable[58] = reinterpret_cast<void*>(FakeDeviceGetRenderState);
        g_fakeDeviceVTable[59] = reinterpret_cast<void*>(FakeDeviceCreateStateBlock);
        g_fakeDeviceVTable[60] = reinterpret_cast<void*>(FakeDeviceBeginStateBlock);
        g_fakeDeviceVTable[61] = reinterpret_cast<void*>(FakeDeviceEndStateBlock);
        g_fakeDeviceVTable[67] = reinterpret_cast<void*>(FakeDeviceSetTextureStageState);
        g_fakeDeviceVTable[86] = reinterpret_cast<void*>(FakeDeviceCreateVertexDeclaration);
        g_fakeDeviceVTable[87] = reinterpret_cast<void*>(FakeDeviceSetVertexDeclaration);
        g_fakeDeviceVTable[89] = reinterpret_cast<void*>(FakeDeviceSetFVF);
        g_fakeDeviceVTable[100] = reinterpret_cast<void*>(FakeDeviceSetStreamSource);
        g_fakeDeviceVTable[102] = reinterpret_cast<void*>(FakeDeviceSetStreamSourceFreq);
        g_fakeDeviceVTable[104] = reinterpret_cast<void*>(FakeDeviceSetIndices);
        g_fakeDeviceVTable[26] = reinterpret_cast<void*>(FakeDeviceCreateVertexBuffer);
        g_fakeDeviceVTable[27] = reinterpret_cast<void*>(FakeDeviceCreateIndexBuffer);
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
    BuildSyntheticVs3Shader();
    BuildSyntheticPs3Shader();

    // First touch the real export so the executable has a normal d3d9.dll
    // import and its IAT points to the system export before we replace it.
    IDirect3D9* realD3D = Direct3DCreate9(D3D_SDK_VERSION);
    if (!realD3D)
        return Fail("Real Direct3DCreate9 export returned NULL");
    realD3D->Release();

    if (!PatchImportToFakeCreate9())
        return Fail("Could not patch the synthetic host IAT to its fake D3D9 factory");
    std::printf(
        "SMOKE: fake state-block vtable slots create=%p begin=%p end=%p\\n",
        g_fakeDeviceVTable[59], g_fakeDeviceVTable[60], g_fakeDeviceVTable[61]);
    std::fflush(stdout);

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
        L"General", L"EnableFrameProfiler", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"FrameProfilerWindowFrames", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"EnableRedundantStateCache", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"EnableBindingCache", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"EnableShaderConstantCache", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"StateCacheReportFrames", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"CaptureShaderConstants", L"1", iniPath);
    WritePrivateProfileStringW(
        L"General", L"CaptureShaderConstantMaxRecords", L"6", iniPath);
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
    if (!CopyFileW(
        L"build\\out\\basic_vs20.vso",
        L"build\\bin\\IVLegacyFallbacks\\smoke.vs20.vso",
        FALSE))
    {
        return Fail("Could not stage synthetic VS2 fallback bytecode");
    }

    const unsigned __int64 syntheticVertexHash = HashShaderBytes(
        reinterpret_cast<const BYTE*>(g_syntheticVs3VertexShader),
        sizeof(g_syntheticVs3VertexShader));
    wchar_t syntheticVertexHashKey[32] = {};
    _snwprintf_s(
        syntheticVertexHashKey,
        _countof(syntheticVertexHashKey),
        _TRUNCATE,
        L"%016llX",
        syntheticVertexHash);
    const wchar_t* fallbackIniPath = L"build\\bin\\IVLegacyShaderFallbacks.ini";
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
    DeleteFileW(fallbackIniPath);
    if (!WritePrivateProfileStringW(
        L"ShaderFallbacks",
        syntheticHashKey,
        L"IVLegacyFallbacks\\smoke.ps20.pso",
        fallbackIniPath) ||
        !WritePrivateProfileStringW(
            L"VertexShaderFallbacks",
            syntheticVertexHashKey,
            L"IVLegacyFallbacks\\smoke.vs20.vso",
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
    if (InterlockedCompareExchange(&g_fakeGetRenderTargetCount, 0, 0) < 4 ||
        InterlockedCompareExchange(&g_fakeGetDepthStencilSurfaceCount, 0, 0) < 1)
        return Fail("initial surface inventory did not call the typed D3D9 getter slots");

    D3DCAPS9 deviceCaps = {};
    const HRESULT deviceCapsHr = device->GetDeviceCaps(&deviceCaps);

    HRESULT resetHr = device->Reset(&parameters);
    if (InterlockedCompareExchange(&g_fakeGetRenderTargetCount, 0, 0) < 8 ||
        InterlockedCompareExchange(&g_fakeGetDepthStencilSurfaceCount, 0, 0) < 2)
        return Fail("surface inventory was not refreshed after successful Reset");
    HRESULT presentHr = device->Present(NULL, NULL, NULL, NULL);

    IDirect3DSurface9* renderTarget = NULL;
    const HRESULT renderTargetHr = device->CreateRenderTarget(
        32, 32, D3DFMT_A8R8G8B8,
        D3DMULTISAMPLE_NONE, 0, FALSE, &renderTarget, NULL);

    IDirect3DSurface9* depthSurface = NULL;
    const HRESULT depthSurfaceHr = device->CreateDepthStencilSurface(
        32, 32, D3DFMT_D24S8,
        D3DMULTISAMPLE_NONE, 0, TRUE, &depthSurface, NULL);

    D3DVIEWPORT9 viewport = {};
    viewport.X = 0;
    viewport.Y = 0;
    viewport.Width = 64;
    viewport.Height = 48;
    viewport.MinZ = 0.0f;
    viewport.MaxZ = 1.0f;
    const HRESULT setViewportHr = device->SetViewport(&viewport);
    if (FAILED(setViewportHr) ||
        InterlockedCompareExchange(&g_fakeSetViewportCalls, 0, 0) != 1)
        return Fail("SetViewport slot 47 was not forwarded through the telemetry hook");

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
    IDirect3DVertexShader9* fallbackVertexShader = NULL;
    IDirect3DPixelShader9* fallbackPixelShader = NULL;
    IDirect3DPixelShader9* unmappedPixelShader = NULL;
    IDirect3DPixelShader9* pixelShader = NULL;
    HRESULT vertexShaderHr = D3DERR_INVALIDCALL;
    HRESULT fallbackVertexShaderHr = D3DERR_INVALIDCALL;
    HRESULT pixelShaderHr = D3DERR_INVALIDCALL;
    HRESULT fallbackShaderHr = D3DERR_INVALIDCALL;
    HRESULT unmappedShaderHr = D3DERR_INVALIDCALL;
    DWORD mappedVertexShaderVersion = 0;
    DWORD mappedShaderVersion = 0;
    DWORD unmappedShaderVersion = 0;

    if (vertexBytecode)
        vertexShaderHr = device->CreateVertexShader(
            reinterpret_cast<const DWORD*>(vertexBytecode), &vertexShader);

    fallbackVertexShaderHr = device->CreateVertexShader(
        g_syntheticVs3VertexShader, &fallbackVertexShader);
    mappedVertexShaderVersion = g_fakeLastVertexShaderVersion;

    fallbackShaderHr = device->CreatePixelShader(
        g_syntheticPs3PixelShader, &fallbackPixelShader);
    mappedShaderVersion = g_fakeLastPixelShaderVersion;

    unmappedShaderHr = device->CreatePixelShader(
        g_syntheticPs3PixelShaderAlt, &unmappedPixelShader);
    unmappedShaderVersion = g_fakeLastPixelShaderVersion;

    if (pixelBytecode)
        pixelShaderHr = device->CreatePixelShader(
            reinterpret_cast<const DWORD*>(pixelBytecode), &pixelShader);

    const HRESULT setVertexShaderHr = device->SetVertexShader(fallbackVertexShader);
    const LONG vsCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetVertexShaderCalls, 0, 0);
    device->SetVertexShader(fallbackVertexShader);
    device->SetVertexShader(fallbackVertexShader);
    device->SetVertexShader(NULL);
    device->SetVertexShader(NULL);
    device->SetVertexShader(fallbackVertexShader);
    if (InterlockedCompareExchange(&g_fakeSetVertexShaderCalls, 0, 0) -
        vsCallsBeforeCacheTest != 2)
        return Fail("vertex-shader binding cache did not suppress duplicates or forward changes");
    // Draw with the actual PS2 replacement object to test end-to-end correlation.
    const HRESULT setPixelShaderHr = device->SetPixelShader(fallbackPixelShader);
    const LONG psCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetPixelShaderCalls, 0, 0);
    device->SetPixelShader(fallbackPixelShader);
    device->SetPixelShader(fallbackPixelShader);
    device->SetPixelShader(NULL);
    device->SetPixelShader(NULL);
    device->SetPixelShader(fallbackPixelShader);
    if (InterlockedCompareExchange(&g_fakeSetPixelShaderCalls, 0, 0) -
        psCallsBeforeCacheTest != 2)
        return Fail("pixel-shader binding cache did not suppress duplicates or forward changes");

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
    const LONG textureCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetTextureCalls, 0, 0);
    device->SetTexture(0, reinterpret_cast<IDirect3DBaseTexture9*>(fakeTexture));
    device->SetTexture(0, reinterpret_cast<IDirect3DBaseTexture9*>(fakeTexture));
    device->SetTexture(0, NULL);
    device->SetTexture(0, NULL);
    device->SetTexture(0, reinterpret_cast<IDirect3DBaseTexture9*>(fakeTexture));
    if (InterlockedCompareExchange(&g_fakeSetTextureCalls, 0, 0) -
        textureCallsBeforeCacheTest != 2)
        return Fail("texture binding cache did not suppress duplicate bindings and preserve changed bindings");
    const HRESULT setSamplerStateHr = device->SetSamplerState(
        0, D3DSAMP_MINFILTER, D3DTEXF_POINT);
    const HRESULT setRenderStateHr = device->SetRenderState(
        D3DRS_ALPHABLENDENABLE, TRUE);
    const HRESULT setTextureStageStateHr = device->SetTextureStageState(
        0, D3DTSS_COLOROP, D3DTOP_MODULATE);

    // GetRenderState is slot 58 and must remain untouched. Older incorrect
    // state-block hook indices replaced this read method and disabled/corrupted
    // the cache before the BeginStateBlock test could run.
    DWORD queriedRenderState = 0xFFFFFFFFUL;
    const LONG getRenderStateCallsBefore =
        InterlockedCompareExchange(&g_fakeGetRenderStateCalls, 0, 0);
    const HRESULT getRenderStateHr = device->GetRenderState(
        D3DRS_ZENABLE, &queriedRenderState);
    if (FAILED(getRenderStateHr) || queriedRenderState != 0 ||
        InterlockedCompareExchange(&g_fakeGetRenderStateCalls, 0, 0) -
            getRenderStateCallsBefore != 1)
        return Fail("GetRenderState slot 58 was overwritten by a state-block hook");

    // Each group submits one new value, repeats it (cache hit), changes it,
    // then repeats the changed value (second cache hit).
    const LONG renderCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetRenderStateCalls, 0, 0);
    device->SetRenderState(D3DRS_ZENABLE, TRUE);
    device->SetRenderState(D3DRS_ZENABLE, TRUE);
    device->SetRenderState(D3DRS_ZENABLE, FALSE);
    device->SetRenderState(D3DRS_ZENABLE, FALSE);
    if (InterlockedCompareExchange(&g_fakeSetRenderStateCalls, 0, 0) -
        renderCallsBeforeCacheTest != 2)
        return Fail("redundant render-state calls were not suppressed exactly twice");

    const LONG stageCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetTextureStageStateCalls, 0, 0);
    device->SetTextureStageState(0, D3DTSS_ALPHAOP, D3DTOP_MODULATE);
    device->SetTextureStageState(0, D3DTSS_ALPHAOP, D3DTOP_MODULATE);
    device->SetTextureStageState(0, D3DTSS_ALPHAOP, D3DTOP_ADD);
    device->SetTextureStageState(0, D3DTSS_ALPHAOP, D3DTOP_ADD);
    if (InterlockedCompareExchange(&g_fakeSetTextureStageStateCalls, 0, 0) -
        stageCallsBeforeCacheTest != 2)
        return Fail("redundant texture-stage calls were not suppressed exactly twice");

    const LONG samplerCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetSamplerStateCalls, 0, 0);
    device->SetSamplerState(0, D3DSAMP_MAGFILTER, D3DTEXF_LINEAR);
    device->SetSamplerState(0, D3DSAMP_MAGFILTER, D3DTEXF_LINEAR);
    device->SetSamplerState(0, D3DSAMP_MAGFILTER, D3DTEXF_POINT);
    device->SetSamplerState(0, D3DSAMP_MAGFILTER, D3DTEXF_POINT);
    if (InterlockedCompareExchange(&g_fakeSetSamplerStateCalls, 0, 0) -
        samplerCallsBeforeCacheTest != 2)
        return Fail("redundant sampler-state calls were not suppressed exactly twice");

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

    const float changedVertexConstants[4] = { 9.0f, 8.0f, 7.0f, 6.0f };
    const float changedPixelConstants[4] = { 0.9f, 0.8f, 0.7f, 0.6f };
    const int changedVertexIntegerConstants[4] = { 9, 8, 7, 6 };
    const int changedPixelIntegerConstants[4] = { 5, 4, 3, 2 };
    const BOOL changedVertexBooleanConstants[2] = { TRUE, TRUE };
    const BOOL changedPixelBooleanConstants[2] = { FALSE, FALSE };

    const LONG vsFloatCallsBeforeCache =
        InterlockedCompareExchange(&g_fakeSetVertexFloatConstantsCalls, 0, 0);
    device->SetVertexShaderConstantF(4, vertexConstants, 1);
    device->SetVertexShaderConstantF(4, vertexConstants, 1);
    device->SetVertexShaderConstantF(4, changedVertexConstants, 1);
    device->SetVertexShaderConstantF(4, changedVertexConstants, 1);
    device->SetVertexShaderConstantF(4, vertexConstants, 1);
    if (InterlockedCompareExchange(&g_fakeSetVertexFloatConstantsCalls, 0, 0) -
        vsFloatCallsBeforeCache != 2)
        return Fail("vertex float-constant cache did not skip exact ranges and forward changed values");

    const LONG psFloatCallsBeforeCache =
        InterlockedCompareExchange(&g_fakeSetPixelFloatConstantsCalls, 0, 0);
    device->SetPixelShaderConstantF(7, pixelConstants, 1);
    device->SetPixelShaderConstantF(7, pixelConstants, 1);
    device->SetPixelShaderConstantF(7, changedPixelConstants, 1);
    device->SetPixelShaderConstantF(7, changedPixelConstants, 1);
    device->SetPixelShaderConstantF(7, pixelConstants, 1);
    if (InterlockedCompareExchange(&g_fakeSetPixelFloatConstantsCalls, 0, 0) -
        psFloatCallsBeforeCache != 2)
        return Fail("pixel float-constant cache did not skip exact ranges and forward changed values");

    const LONG vsIntegerCallsBeforeCache =
        InterlockedCompareExchange(&g_fakeSetVertexIntegerConstantsCalls, 0, 0);
    device->SetVertexShaderConstantI(2, vertexIntegerConstants, 1);
    device->SetVertexShaderConstantI(2, vertexIntegerConstants, 1);
    device->SetVertexShaderConstantI(2, changedVertexIntegerConstants, 1);
    device->SetVertexShaderConstantI(2, changedVertexIntegerConstants, 1);
    device->SetVertexShaderConstantI(2, vertexIntegerConstants, 1);
    if (InterlockedCompareExchange(&g_fakeSetVertexIntegerConstantsCalls, 0, 0) -
        vsIntegerCallsBeforeCache != 2)
        return Fail("vertex integer-constant cache did not skip exact ranges and forward changed values");

    const LONG psIntegerCallsBeforeCache =
        InterlockedCompareExchange(&g_fakeSetPixelIntegerConstantsCalls, 0, 0);
    device->SetPixelShaderConstantI(1, pixelIntegerConstants, 1);
    device->SetPixelShaderConstantI(1, pixelIntegerConstants, 1);
    device->SetPixelShaderConstantI(1, changedPixelIntegerConstants, 1);
    device->SetPixelShaderConstantI(1, changedPixelIntegerConstants, 1);
    device->SetPixelShaderConstantI(1, pixelIntegerConstants, 1);
    if (InterlockedCompareExchange(&g_fakeSetPixelIntegerConstantsCalls, 0, 0) -
        psIntegerCallsBeforeCache != 2)
        return Fail("pixel integer-constant cache did not skip exact ranges and forward changed values");

    const LONG vsBooleanCallsBeforeCache =
        InterlockedCompareExchange(&g_fakeSetVertexBooleanConstantsCalls, 0, 0);
    device->SetVertexShaderConstantB(4, vertexBooleanConstants, 2);
    device->SetVertexShaderConstantB(4, vertexBooleanConstants, 2);
    device->SetVertexShaderConstantB(4, changedVertexBooleanConstants, 2);
    device->SetVertexShaderConstantB(4, changedVertexBooleanConstants, 2);
    device->SetVertexShaderConstantB(4, vertexBooleanConstants, 2);
    if (InterlockedCompareExchange(&g_fakeSetVertexBooleanConstantsCalls, 0, 0) -
        vsBooleanCallsBeforeCache != 2)
        return Fail("vertex boolean-constant cache did not skip exact ranges and forward changed values");

    const LONG psBooleanCallsBeforeCache =
        InterlockedCompareExchange(&g_fakeSetPixelBooleanConstantsCalls, 0, 0);
    device->SetPixelShaderConstantB(5, pixelBooleanConstants, 2);
    device->SetPixelShaderConstantB(5, pixelBooleanConstants, 2);
    device->SetPixelShaderConstantB(5, changedPixelBooleanConstants, 2);
    device->SetPixelShaderConstantB(5, changedPixelBooleanConstants, 2);
    device->SetPixelShaderConstantB(5, pixelBooleanConstants, 2);
    if (InterlockedCompareExchange(&g_fakeSetPixelBooleanConstantsCalls, 0, 0) -
        psBooleanCallsBeforeCache != 2)
        return Fail("pixel boolean-constant cache did not skip exact ranges and forward changed values");

    D3DVERTEXELEMENT9 declarationElements[3] = {};
    declarationElements[0].Stream = 0;
    declarationElements[0].Offset = 0;
    declarationElements[0].Type = D3DDECLTYPE_FLOAT3;
    declarationElements[0].Method = D3DDECLMETHOD_DEFAULT;
    declarationElements[0].Usage = D3DDECLUSAGE_POSITION;
    declarationElements[0].UsageIndex = 0;
    declarationElements[1].Stream = 0;
    declarationElements[1].Offset = 12;
    declarationElements[1].Type = D3DDECLTYPE_FLOAT2;
    declarationElements[1].Method = D3DDECLMETHOD_DEFAULT;
    declarationElements[1].Usage = D3DDECLUSAGE_TEXCOORD;
    declarationElements[1].UsageIndex = 0;
    declarationElements[2].Stream = 0xFF;
    declarationElements[2].Type = D3DDECLTYPE_UNUSED;

    IDirect3DVertexDeclaration9* vertexDeclaration = NULL;
    const HRESULT createVertexDeclarationHr = device->CreateVertexDeclaration(
        declarationElements, &vertexDeclaration);
    const HRESULT setVertexDeclarationHr = device->SetVertexDeclaration(vertexDeclaration);
    const LONG declarationCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetVertexDeclarationCalls, 0, 0);
    device->SetVertexDeclaration(vertexDeclaration);
    device->SetVertexDeclaration(vertexDeclaration);
    if (InterlockedCompareExchange(&g_fakeSetVertexDeclarationCalls, 0, 0) -
        declarationCallsBeforeCacheTest != 0)
        return Fail("vertex-declaration cache did not suppress identical layout bindings");
    IDirect3DVertexBuffer9* fakeVertexBuffer = NULL;
    IDirect3DIndexBuffer9* fakeIndexBuffer = NULL;
    const HRESULT createVertexBufferHr = device->CreateVertexBuffer(
        4096, D3DUSAGE_WRITEONLY, 0, D3DPOOL_MANAGED, &fakeVertexBuffer, NULL);
    const HRESULT createIndexBufferHr = device->CreateIndexBuffer(
        1024, D3DUSAGE_WRITEONLY, D3DFMT_INDEX16, D3DPOOL_MANAGED, &fakeIndexBuffer, NULL);
    const HRESULT setStreamSourceHr = device->SetStreamSource(
        0, fakeVertexBuffer, 0, 20);
    const LONG streamCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetStreamSourceCalls, 0, 0);
    device->SetStreamSource(0, fakeVertexBuffer, 0, 20);
    device->SetStreamSource(0, fakeVertexBuffer, 0, 20);
    device->SetStreamSource(0, fakeVertexBuffer, 4, 20);
    device->SetStreamSource(0, fakeVertexBuffer, 4, 20);
    device->SetStreamSource(0, fakeVertexBuffer, 0, 20);
    if (InterlockedCompareExchange(&g_fakeSetStreamSourceCalls, 0, 0) -
        streamCallsBeforeCacheTest != 2)
        return Fail("vertex-stream cache did not compare buffer, offset and stride correctly");
    const HRESULT setStreamSourceFreqHr = device->SetStreamSourceFreq(0, 1);
    const LONG streamFrequencyCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetStreamSourceFreqCalls, 0, 0);
    device->SetStreamSourceFreq(0, 1);
    device->SetStreamSourceFreq(0, 1);
    device->SetStreamSourceFreq(0, 2);
    device->SetStreamSourceFreq(0, 2);
    device->SetStreamSourceFreq(0, 1);
    if (InterlockedCompareExchange(&g_fakeSetStreamSourceFreqCalls, 0, 0) -
        streamFrequencyCallsBeforeCacheTest != 2)
        return Fail("stream-frequency cache did not suppress identical divider state and forward changes");
    const HRESULT setIndicesHr = device->SetIndices(fakeIndexBuffer);
    const LONG indicesCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetIndicesCalls, 0, 0);
    device->SetIndices(fakeIndexBuffer);
    device->SetIndices(fakeIndexBuffer);
    device->SetIndices(NULL);
    device->SetIndices(NULL);
    device->SetIndices(fakeIndexBuffer);
    if (InterlockedCompareExchange(&g_fakeSetIndicesCalls, 0, 0) -
        indicesCallsBeforeCacheTest != 2)
        return Fail("index-buffer cache did not suppress duplicate and preserve changed bindings");

    const HRESULT drawPrimitiveHr = device->DrawPrimitive(
        D3DPT_TRIANGLELIST, 0, 1);
    const DWORD smokeFVF = D3DFVF_XYZ | D3DFVF_TEX1;
    const HRESULT setFVFHr = device->SetFVF(smokeFVF);
    const LONG fvfCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetFVFCalls, 0, 0);
    device->SetFVF(smokeFVF);
    device->SetFVF(smokeFVF);
    if (InterlockedCompareExchange(&g_fakeSetFVFCalls, 0, 0) -
        fvfCallsBeforeCacheTest != 0)
        return Fail("FVF cache did not suppress identical FVF bindings");
    const HRESULT drawIndexedPrimitiveHr = device->DrawIndexedPrimitive(
        D3DPT_TRIANGLELIST, 0, 0, 3, 0, 1);
    const HRESULT drawPrimitiveUPHr = device->DrawPrimitiveUP(
        D3DPT_TRIANGLELIST, 1, NULL, sizeof(float) * 3);
    const HRESULT drawIndexedPrimitiveUPHr = device->DrawIndexedPrimitiveUP(
        D3DPT_TRIANGLELIST, 0, 3, 1, NULL, D3DFMT_INDEX16,
        NULL, sizeof(float) * 3);
    const HRESULT profilerPresentHr = device->Present(NULL, NULL, NULL, NULL);
    if (FAILED(profilerPresentHr))
        return Fail("Frame-profiler verification Present call failed");

    // RT0 changes reset the viewport, so the cache must forward the first
    // explicit viewport after that transition and suppress only its duplicate.
    D3DVIEWPORT9 changedViewport = viewport;
    changedViewport.Width = 63;
    const LONG viewportCallsBeforeCacheTest =
        InterlockedCompareExchange(&g_fakeSetViewportCalls, 0, 0);
    device->SetViewport(&viewport);
    device->SetViewport(&viewport);
    device->SetViewport(&changedViewport);
    device->SetViewport(&changedViewport);
    if (InterlockedCompareExchange(&g_fakeSetViewportCalls, 0, 0) -
        viewportCallsBeforeCacheTest != 2)
        return Fail("viewport cache did not suppress exact duplicates or forward changed dimensions");

    // A non-readable constant range must be forwarded and invalidate its
    // previous shadow. The next valid upload of that range must not be skipped.
    const LONG floatCallsBeforeInvalidRange =
        InterlockedCompareExchange(&g_fakeSetVertexFloatConstantsCalls, 0, 0);
    device->SetVertexShaderConstantF(4, NULL, 1);
    device->SetVertexShaderConstantF(4, vertexConstants, 1);
    device->SetVertexShaderConstantF(4, vertexConstants, 1);
    if (InterlockedCompareExchange(&g_fakeSetVertexFloatConstantsCalls, 0, 0) -
        floatCallsBeforeInvalidRange != 2)
        return Fail("unreadable shader-constant input did not invalidate the cached range");

    // Reset must discard the shadowed values; the same value after Reset must
    // reach the original D3D9 setter again.
    const LONG renderCallsBeforeReset =
        InterlockedCompareExchange(&g_fakeSetRenderStateCalls, 0, 0);
    const HRESULT cacheResetHr = device->Reset(&parameters);
    if (FAILED(cacheResetHr))
        return Fail("State-cache reset invalidation test could not Reset the fake device");
    const HRESULT resetStateHr = device->SetRenderState(D3DRS_ZENABLE, FALSE);
    if (FAILED(resetStateHr) ||
        InterlockedCompareExchange(&g_fakeSetRenderStateCalls, 0, 0) -
            renderCallsBeforeReset != 1)
        return Fail("successful Reset did not invalidate cached render-state values");
    const LONG viewportCallsBeforeReset =
        InterlockedCompareExchange(&g_fakeSetViewportCalls, 0, 0);
    device->SetViewport(&changedViewport);
    device->SetViewport(&changedViewport);
    if (InterlockedCompareExchange(&g_fakeSetViewportCalls, 0, 0) -
        viewportCallsBeforeReset != 1)
        return Fail("Reset did not invalidate viewport cache state");

    const LONG textureCallsBeforeBindingReset =
        InterlockedCompareExchange(&g_fakeSetTextureCalls, 0, 0);
    device->SetTexture(0, reinterpret_cast<IDirect3DBaseTexture9*>(fakeTexture));
    device->SetTexture(0, reinterpret_cast<IDirect3DBaseTexture9*>(fakeTexture));
    if (InterlockedCompareExchange(&g_fakeSetTextureCalls, 0, 0) -
        textureCallsBeforeBindingReset != 1)
        return Fail("Reset did not invalidate texture-binding cache state");
    const LONG frequencyCallsBeforeReset =
        InterlockedCompareExchange(&g_fakeSetStreamSourceFreqCalls, 0, 0);
    device->SetStreamSourceFreq(0, 1);
    device->SetStreamSourceFreq(0, 1);
    if (InterlockedCompareExchange(&g_fakeSetStreamSourceFreqCalls, 0, 0) -
        frequencyCallsBeforeReset != 1)
        return Fail("Reset did not invalidate stream-frequency cache state");
    const LONG vsCallsBeforeBindingReset =
        InterlockedCompareExchange(&g_fakeSetVertexShaderCalls, 0, 0);
    device->SetVertexShader(fallbackVertexShader);
    device->SetVertexShader(fallbackVertexShader);
    if (InterlockedCompareExchange(&g_fakeSetVertexShaderCalls, 0, 0) -
        vsCallsBeforeBindingReset != 1)
        return Fail("Reset did not invalidate vertex-shader binding cache state");
    const LONG vsConstantsBeforeResetTest =
        InterlockedCompareExchange(&g_fakeSetVertexFloatConstantsCalls, 0, 0);
    device->SetVertexShaderConstantF(4, vertexConstants, 1);
    device->SetVertexShaderConstantF(4, vertexConstants, 1);
    if (InterlockedCompareExchange(&g_fakeSetVertexFloatConstantsCalls, 0, 0) -
        vsConstantsBeforeResetTest != 1)
        return Fail("Reset did not invalidate shader-constant range cache state");

    const LONG renderCallsBeforeStateBlock =
        InterlockedCompareExchange(&g_fakeSetRenderStateCalls, 0, 0);
    std::printf("SMOKE: before-BeginStateBlock\\n");
    std::fflush(stdout);
    const HRESULT beginStateBlockHr = device->BeginStateBlock();
    std::printf("SMOKE: after-BeginStateBlock hr=0x%08lX calls=%ld\\n",
        static_cast<unsigned long>(beginStateBlockHr),
        InterlockedCompareExchange(&g_fakeBeginStateBlockCalls, 0, 0));
    std::fflush(stdout);
    const HRESULT stateBlockStateHr = device->SetRenderState(D3DRS_ZENABLE, FALSE);
    std::printf("SMOKE: after-stateblock-SetRenderState hr=0x%08lX\\n",
        static_cast<unsigned long>(stateBlockStateHr));
    std::fflush(stdout);
    if (FAILED(beginStateBlockHr) || FAILED(stateBlockStateHr) ||
        InterlockedCompareExchange(&g_fakeBeginStateBlockCalls, 0, 0) != 1 ||
        InterlockedCompareExchange(&g_fakeSetRenderStateCalls, 0, 0) -
            renderCallsBeforeStateBlock != 1)
        return Fail("state-block API use did not disable redundant state suppression");
    const LONG textureCallsBeforeStateBlock =
        InterlockedCompareExchange(&g_fakeSetTextureCalls, 0, 0);
    device->SetTexture(0, reinterpret_cast<IDirect3DBaseTexture9*>(fakeTexture));
    device->SetTexture(0, reinterpret_cast<IDirect3DBaseTexture9*>(fakeTexture));
    if (InterlockedCompareExchange(&g_fakeSetTextureCalls, 0, 0) -
        textureCallsBeforeStateBlock != 2)
        return Fail("state-block API use did not disable texture-binding suppression");
    const LONG frequencyCallsBeforeStateBlock =
        InterlockedCompareExchange(&g_fakeSetStreamSourceFreqCalls, 0, 0);
    device->SetStreamSourceFreq(0, 1);
    device->SetStreamSourceFreq(0, 1);
    if (InterlockedCompareExchange(&g_fakeSetStreamSourceFreqCalls, 0, 0) -
        frequencyCallsBeforeStateBlock != 2)
        return Fail("state-block API use did not disable stream-frequency suppression");
    const LONG shaderCallsBeforeStateBlock =
        InterlockedCompareExchange(&g_fakeSetVertexShaderCalls, 0, 0);
    device->SetVertexShader(fallbackVertexShader);
    device->SetVertexShader(fallbackVertexShader);
    if (InterlockedCompareExchange(&g_fakeSetVertexShaderCalls, 0, 0) -
        shaderCallsBeforeStateBlock != 2)
        return Fail("state-block API use did not disable shader-binding suppression");
    const LONG constantsBeforeStateBlock =
        InterlockedCompareExchange(&g_fakeSetVertexFloatConstantsCalls, 0, 0);
    device->SetVertexShaderConstantF(4, vertexConstants, 1);
    device->SetVertexShaderConstantF(4, vertexConstants, 1);
    if (InterlockedCompareExchange(&g_fakeSetVertexFloatConstantsCalls, 0, 0) -
        constantsBeforeStateBlock != 2)
        return Fail("state-block API use did not disable shader-constant suppression");

    IDirect3DStateBlock9* createdStateBlock = NULL;
    const HRESULT createStateBlockHr = device->CreateStateBlock(
        D3DSBT_ALL, &createdStateBlock);
    IDirect3DStateBlock9* endedStateBlock = NULL;
    const HRESULT endStateBlockHr = device->EndStateBlock(&endedStateBlock);
    if (createStateBlockHr != D3DERR_INVALIDCALL || endStateBlockHr != D3DERR_INVALIDCALL ||
        InterlockedCompareExchange(&g_fakeCreateStateBlockCalls, 0, 0) != 1 ||
        InterlockedCompareExchange(&g_fakeEndStateBlockCalls, 0, 0) != 1)
        return Fail("CreateStateBlock/EndStateBlock vtable hooks did not preserve their original signatures");

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
    if (fallbackVertexShader)
        fallbackVertexShader->Release();
    if (fallbackPixelShader)
        fallbackPixelShader->Release();
    if (fakeTexture)
        fakeTexture->Release();
    if (vertexDeclaration)
        vertexDeclaration->Release();
    if (fakeVertexBuffer)
        fakeVertexBuffer->Release();
    if (fakeIndexBuffer)
        fakeIndexBuffer->Release();
    device->Release();
    d3d->Release();

    if (!WaitForLog("DIRECT3DCREATE9", 5000))
        return Fail("Direct3DCreate9 wrapper was not called");
    if (!HasText("D3D9_ADAPTER"))
        return Fail("IDirect3D9::GetAdapterIdentifier hook was not observed");
    if (!HasText("D3D9_GET_DEVICE_CAPS") ||
        !HasText("HWTransformAndLight=1"))
        return Fail("IDirect3D9 capability audit did not record the synthetic HW T&L bit");
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
    if (!HasText("request_software_vp=1"))
        return Fail("CreateDevice did not record the requested software vertex-processing mode");
    if (!HasText("DEVICE_RESET_REQUEST") || !HasText("DEVICE_RESET_RESULT"))
        return Fail("IDirect3DDevice9::Reset hook was not observed");
    if (!HasText("CREATE_RENDER_TARGET") || !HasText("CREATE_DEPTH_STENCIL_SURFACE"))
        return Fail("Device render/depth surface creation hooks were not observed");
    if (!HasText("CREATE_VERTEX_SHADER") || !HasText("CREATE_PIXEL_SHADER"))
        return Fail("Device shader creation hooks were not observed");
    if (!HasText("VERTEX_SHADER_FALLBACK_ATTEMPT") ||
        !HasText("VERTEX_SHADER_FALLBACK_APPLIED") ||
        !HasText("VERTEX_SHADER_FALLBACK_OBJECT_MAP"))
        return Fail("Configured VS2 fallback was not applied to the matching VS3 shader");
    if (FAILED(fallbackVertexShaderHr) ||
        mappedVertexShaderVersion != 0xFFFE0200UL)
        return Fail("Hash-mapped VS2 replacement did not preserve the expected VS2 profile");
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
    if (!HasText("FRAME_PROFILER_ENABLED") ||
        !HasText("FRAME_PROFILE_WINDOW samples=1") ||
        !HasText("avg_draw_calls=4.00") ||
        !HasText("gpu_time=not_measured"))
        return Fail("Frame-profiler summary did not record the synthetic frame and four draw calls");
    if (!HasText("REDUNDANT_STATE_CACHE_ENABLED") ||
        !HasText("D3D9_STATE_CACHE_WINDOW") ||
        !HasText("render_forwarded=3 render_skipped=2") ||
        !HasText("texture_stage_forwarded=3 texture_stage_skipped=2") ||
        !HasText("sampler_forwarded=3 sampler_skipped=2"))
        return Fail("State-cache counters did not report the expected forwarded and skipped setter calls");
    if (!HasText("BINDING_CACHE_ENABLED") ||
        !HasText("D3D9_BINDING_CACHE_WINDOW") ||
        !HasText("texture_forwarded=3 texture_skipped=3") ||
        !HasText("stream_forwarded=3 stream_skipped=3") ||
        !HasText("stream_freq_forwarded=3 stream_freq_skipped=3") ||
        !HasText("index_forwarded=3 index_skipped=3") ||
        !HasText("vs_forwarded=3 vs_skipped=3") ||
        !HasText("ps_forwarded=3 ps_skipped=3") ||
        !HasText("vertex_format_forwarded=2 vertex_format_skipped=4"))
        return Fail("Binding-cache counters did not report expected texture/stream/index/shader/format suppression");
    if (!HasText("SHADER_CONSTANT_CACHE_ENABLED") ||
        !HasText("D3D9_SHADER_CONSTANT_CACHE_WINDOW") ||
        !HasText("vs_float_forwarded=3 vs_float_skipped=3") ||
        !HasText("ps_float_forwarded=3 ps_float_skipped=3") ||
        !HasText("vs_int_forwarded=3 vs_int_skipped=3") ||
        !HasText("ps_int_forwarded=3 ps_int_skipped=3") ||
        !HasText("vs_bool_forwarded=3 vs_bool_skipped=3") ||
        !HasText("ps_bool_forwarded=3 ps_bool_skipped=3"))
        return Fail("Shader constant cache did not suppress unchanged float/integer/boolean register ranges");
    if (!HasText("STATE_CACHE_DISABLED reason=state_block_api_used") ||
        !HasText("BINDING_CACHE_DISABLED reason=state_block_api_used") ||
        !HasText("SHADER_CONSTANT_CACHE_DISABLED reason=state_block_api_used") ||
        !HasText("STATE_BLOCK_BEGIN_FORWARD") ||
        !HasText("STATE_BLOCK_BEGIN_RETURN") ||
        !HasText("STATE_BLOCK_CREATE_RETURN") ||
        !HasText("STATE_BLOCK_END_RETURN"))
        return Fail("State-block hooks did not preserve the three original D3D9 API call paths");
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
    // Two distinct indices in each group are established before the first
    // draw: ALPHABLENDENABLE + ZENABLE, and COLOROP + ALPHAOP.
    if (!HasText("SET_RENDER_STATE") ||
        !HasText("SET_TEXTURE_STAGE_STATE") ||
        !HasText("render_state_count=2") ||
        !HasText("texture_stage_count=2"))
        return Fail("D3D9 render-state or texture-stage snapshot hooks were not observed");
    if (!HasText("VERTEX_DECL_OBJECT_CREATED") ||
        !HasText("VERTEX_DECL_ELEMENT") ||
        !HasText("BUFFER_OBJECT_CREATED type=VB") ||
        !HasText("BUFFER_OBJECT_CREATED type=IB") ||
        !HasText("SET_VERTEX_DECLARATION") ||
        !HasText("SET_FVF") ||
        !HasText("SET_STREAM_SOURCE") ||
        !HasText("SET_STREAM_SOURCE_FREQ") ||
        !HasText("SET_INDICES") ||
        !HasText("vertex_decl=") ||
        !HasText("streams="))
        return Fail("D3D9 vertex declaration, buffer, FVF, stream or index telemetry was not observed");
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
