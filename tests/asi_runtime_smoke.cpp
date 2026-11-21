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
    std::printf("%s\n", buffer);

    // The ASI remains loaded until process exit because its IAT/vtable hooks
    // point into the module; hot-unloading it would leave dangling callbacks.
    (void)asi;
    return 0;
}
