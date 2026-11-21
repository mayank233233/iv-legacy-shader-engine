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

    bool HasText(const char* marker)
    {
        char buffer[32768] = {};
        if (!ReadLog(buffer, sizeof(buffer)))
            return false;
        return strstr(buffer, marker) != NULL;
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
    const HRESULT formatHr = d3d->CheckDeviceFormat(
        0, D3DDEVTYPE_HAL, D3DFMT_X8R8G8B8,
        D3DUSAGE_RENDERTARGET, D3DRTYPE_TEXTURE, D3DFMT_A8R8G8B8);
    const HRESULT depthHr = d3d->CheckDepthStencilMatch(
        0, D3DDEVTYPE_HAL, D3DFMT_X8R8G8B8,
        D3DFMT_A8R8G8B8, D3DFMT_D24S8);

    WNDCLASSW windowClass = {};
    windowClass.lpfnWndProc = DefWindowProcW;
    windowClass.hInstance = GetModuleHandleW(NULL);
    windowClass.lpszClassName = L"IVLegacyASI_SmokeWindow";
    RegisterClassW(&windowClass);

    HWND window = CreateWindowExW(
        0,
        windowClass.lpszClassName,
        L"IV Legacy ASI smoke test",
        WS_OVERLAPPEDWINDOW,
        0, 0, 96, 96,
        NULL, NULL, windowClass.hInstance, NULL);
    if (!window)
    {
        d3d->Release();
        return Fail("Could not create hidden D3D9 test window");
    }

    D3DPRESENT_PARAMETERS parameters = {};
    parameters.BackBufferWidth = 64;
    parameters.BackBufferHeight = 64;
    parameters.BackBufferFormat = D3DFMT_UNKNOWN;
    parameters.BackBufferCount = 1;
    parameters.SwapEffect = D3DSWAPEFFECT_DISCARD;
    parameters.hDeviceWindow = window;
    parameters.Windowed = TRUE;
    parameters.EnableAutoDepthStencil = FALSE;
    parameters.PresentationInterval = D3DPRESENT_INTERVAL_IMMEDIATE;

    IDirect3DDevice9* device = NULL;
    const HRESULT createDeviceHr = d3d->CreateDevice(
        0,
        D3DDEVTYPE_HAL,
        window,
        D3DCREATE_SOFTWARE_VERTEXPROCESSING,
        &parameters,
        &device);

    HRESULT deviceCapsHr = D3DERR_NOTAVAILABLE;
    HRESULT renderTargetHr = D3DERR_NOTAVAILABLE;
    HRESULT depthSurfaceHr = D3DERR_NOTAVAILABLE;
    HRESULT setRenderTargetHr = D3DERR_NOTAVAILABLE;
    HRESULT setDepthSurfaceHr = D3DERR_NOTAVAILABLE;
    HRESULT vertexShaderHr = D3DERR_NOTAVAILABLE;
    HRESULT pixelShaderHr = D3DERR_NOTAVAILABLE;

    IDirect3DSurface9* renderTarget = NULL;
    IDirect3DSurface9* depthSurface = NULL;
    IDirect3DVertexShader9* vertexShader = NULL;
    IDirect3DPixelShader9* pixelShader = NULL;
    BYTE* vertexBytecode = NULL;
    BYTE* pixelBytecode = NULL;
    DWORD vertexBytecodeSize = 0;
    DWORD pixelBytecodeSize = 0;

    if (SUCCEEDED(createDeviceHr) && device)
    {
        D3DCAPS9 deviceCaps = {};
        deviceCapsHr = device->GetDeviceCaps(&deviceCaps);

        renderTargetHr = device->CreateRenderTarget(
            32, 32, D3DFMT_A8R8G8B8,
            D3DMULTISAMPLE_NONE, 0, FALSE, &renderTarget, NULL);
        if (SUCCEEDED(renderTargetHr) && renderTarget)
            setRenderTargetHr = device->SetRenderTarget(0, renderTarget);

        depthSurfaceHr = device->CreateDepthStencilSurface(
            32, 32, D3DFMT_D24S8,
            D3DMULTISAMPLE_NONE, 0, TRUE, &depthSurface, NULL);
        if (SUCCEEDED(depthSurfaceHr) && depthSurface)
            setDepthSurfaceHr = device->SetDepthStencilSurface(depthSurface);

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

        if (vertexBytecode)
        {
            vertexShaderHr = device->CreateVertexShader(
                reinterpret_cast<const DWORD*>(vertexBytecode), &vertexShader);
        }
        if (pixelBytecode)
        {
            pixelShaderHr = device->CreatePixelShader(
                reinterpret_cast<const DWORD*>(pixelBytecode), &pixelShader);
        }
    }

    if (renderTarget)
        renderTarget->Release();
    if (depthSurface)
        depthSurface->Release();
    if (vertexShader)
        vertexShader->Release();
    if (pixelShader)
        pixelShader->Release();
    if (vertexBytecode)
        HeapFree(GetProcessHeap(), 0, vertexBytecode);
    if (pixelBytecode)
        HeapFree(GetProcessHeap(), 0, pixelBytecode);
    if (device)
        device->Release();
    DestroyWindow(window);
    UnregisterClassW(windowClass.lpszClassName, windowClass.hInstance);
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

    if (SUCCEEDED(createDeviceHr))
    {
        if (!HasText("D3D9_DEVICE_HOOK_INSTALLED"))
            return Fail("IDirect3DDevice9 vtable hook was not installed");
        if (!HasText("DEVICE_GET_DEVICE_CAPS"))
            return Fail("IDirect3DDevice9::GetDeviceCaps hook was not observed");
        if (!HasText("CREATE_RENDER_TARGET") || !HasText("CREATE_DEPTH_STENCIL_SURFACE"))
            return Fail("Device render/depth surface creation hooks were not observed");
        if (!HasText("CREATE_VERTEX_SHADER") || !HasText("CREATE_PIXEL_SHADER"))
            return Fail("Device shader creation hooks were not observed");
    }

    char buffer[32768] = {};
    ReadLog(buffer, sizeof(buffer));
    std::printf("PASS: ASI loaded and D3D9 interface hooks executed.\n");
    std::printf("GetAdapterIdentifier HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(identifierHr));
    std::printf("GetDeviceCaps HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(capsHr));
    std::printf("CheckDeviceFormat HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(formatHr));
    std::printf("CheckDepthStencilMatch HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(depthHr));
    std::printf("CreateDevice HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(createDeviceHr));
    std::printf("DeviceGetCaps HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(deviceCapsHr));
    std::printf("CreateRenderTarget HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(renderTargetHr));
    std::printf("CreateDepthStencilSurface HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(depthSurfaceHr));
    std::printf("SetRenderTarget HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(setRenderTargetHr));
    std::printf("SetDepthStencilSurface HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(setDepthSurfaceHr));
    std::printf("CreateVertexShader HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(vertexShaderHr));
    std::printf("CreatePixelShader HRESULT: 0x%08lX\n",
        static_cast<unsigned long>(pixelShaderHr));
    std::printf("%s\n", buffer);

    // The ASI remains loaded until process exit because its IAT/vtable hooks
    // point into the module; hot-unloading it would leave dangling callbacks.
    (void)asi;
    return 0;
}
