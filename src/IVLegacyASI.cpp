#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <winver.h>
#include <d3d9.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <cwchar>

#pragma comment(lib, "version.lib")

namespace
{
    const UINT kD3D9InterfaceSlots = 17;
    const UINT kD3D9DeviceInterfaceSlots = 119;

    // IDirect3D9 slots, counting IUnknown methods at indexes 0 through 2.
    enum D3D9VTableSlot
    {
        kD3D9GetAdapterIdentifierSlot = 5,
        kD3D9CheckDeviceFormatSlot = 10,
        kD3D9CheckDepthStencilMatchSlot = 12,
        kD3D9GetDeviceCapsSlot = 14,
        kD3D9CreateDeviceSlot = 16
    };

    // IDirect3DDevice9 slots from the D3D9 SDK interface order.
    // CreateVertexShader = 91; CreatePixelShader = 106.
    enum D3D9DeviceVTableSlot
    {
        kDeviceGetDeviceCapsSlot = 7,
        kDeviceResetSlot = 16,
        kDevicePresentSlot = 17,
        kDeviceCreateRenderTargetSlot = 28,
        kDeviceCreateDepthStencilSurfaceSlot = 29,
        kDeviceSetRenderTargetSlot = 37,
        kDeviceSetDepthStencilSurfaceSlot = 39,
        kDeviceCreateVertexShaderSlot = 91,
        kDeviceSetVertexShaderSlot = 92,
        kDeviceCreatePixelShaderSlot = 106,
        kDeviceSetPixelShaderSlot = 107
    };

    HANDLE g_logFile = INVALID_HANDLE_VALUE;
    wchar_t g_gamePath[MAX_PATH] = {};
    wchar_t g_gameDirectory[MAX_PATH] = {};
    wchar_t g_logPath[MAX_PATH] = {};
    wchar_t g_iniPath[MAX_PATH] = {};
    wchar_t g_captureDirectory[MAX_PATH] = {};
    volatile LONG g_logLock = 0;
    volatile LONG g_bootstrapStarted = 0;
    volatile LONG g_bootstrapCompleted = 0;
    volatile LONG g_captureUniqueCount = 0;
    volatile LONG g_capsLogCount = 0;
    volatile LONG g_adapterLogCount = 0;
    volatile LONG g_formatCheckLogCount = 0;
    volatile LONG g_depthMatchLogCount = 0;
    volatile LONG g_vertexShaderLogCount = 0;
    volatile LONG g_pixelShaderLogCount = 0;
    volatile LONG g_setVertexShaderLogCount = 0;
    volatile LONG g_setPixelShaderLogCount = 0;
    volatile LONG g_renderTargetLogCount = 0;
    volatile LONG g_depthTargetCreateLogCount = 0;
    volatile LONG g_setRenderTargetLogCount = 0;
    volatile LONG g_setDepthTargetLogCount = 0;
    BOOL g_telemetryEnabled = TRUE;
    BOOL g_captureShaderBytecode = FALSE;
    DWORD g_captureMaxFiles = 1024;

    typedef IDirect3D9* (WINAPI* Direct3DCreate9Fn)(UINT);
    typedef HRESULT (WINAPI* D3D9GetAdapterIdentifierFn)(
        IDirect3D9*, UINT, DWORD, D3DADAPTER_IDENTIFIER9*);
    typedef HRESULT (WINAPI* D3D9CheckDeviceFormatFn)(
        IDirect3D9*, UINT, D3DDEVTYPE, D3DFORMAT, DWORD, D3DRESOURCETYPE, D3DFORMAT);
    typedef HRESULT (WINAPI* D3D9CheckDepthStencilMatchFn)(
        IDirect3D9*, UINT, D3DDEVTYPE, D3DFORMAT, D3DFORMAT, D3DFORMAT);
    typedef HRESULT (WINAPI* D3D9GetDeviceCapsFn)(
        IDirect3D9*, UINT, D3DDEVTYPE, D3DCAPS9*);
    typedef HRESULT (WINAPI* D3D9CreateDeviceFn)(
        IDirect3D9*, UINT, D3DDEVTYPE, HWND, DWORD,
        D3DPRESENT_PARAMETERS*, IDirect3DDevice9**);

    typedef HRESULT (WINAPI* DeviceGetDeviceCapsFn)(
        IDirect3DDevice9*, D3DCAPS9*);
    typedef HRESULT (WINAPI* DeviceResetFn)(
        IDirect3DDevice9*, D3DPRESENT_PARAMETERS*);
    typedef HRESULT (WINAPI* DevicePresentFn)(
        IDirect3DDevice9*, const RECT*, const RECT*, HWND, const RGNDATA*);
    typedef HRESULT (WINAPI* DeviceCreateRenderTargetFn)(
        IDirect3DDevice9*, UINT, UINT, D3DFORMAT, D3DMULTISAMPLE_TYPE,
        DWORD, BOOL, IDirect3DSurface9**, HANDLE*);
    typedef HRESULT (WINAPI* DeviceCreateDepthStencilSurfaceFn)(
        IDirect3DDevice9*, UINT, UINT, D3DFORMAT, D3DMULTISAMPLE_TYPE,
        DWORD, BOOL, IDirect3DSurface9**, HANDLE*);
    typedef HRESULT (WINAPI* DeviceSetDepthStencilSurfaceFn)(
        IDirect3DDevice9*, IDirect3DSurface9*);
    typedef HRESULT (WINAPI* DeviceSetRenderTargetFn)(
        IDirect3DDevice9*, DWORD, IDirect3DSurface9*);
    typedef HRESULT (WINAPI* DeviceCreateVertexShaderFn)(
        IDirect3DDevice9*, const DWORD*, IDirect3DVertexShader9**);
    typedef HRESULT (WINAPI* DeviceCreatePixelShaderFn)(
        IDirect3DDevice9*, const DWORD*, IDirect3DPixelShader9**);
    typedef HRESULT (WINAPI* DeviceSetVertexShaderFn)(
        IDirect3DDevice9*, IDirect3DVertexShader9*);
    typedef HRESULT (WINAPI* DeviceSetPixelShaderFn)(
        IDirect3DDevice9*, IDirect3DPixelShader9*);

    Direct3DCreate9Fn g_realDirect3DCreate9 = NULL;
    D3D9GetAdapterIdentifierFn g_realD3D9GetAdapterIdentifier = NULL;
    D3D9CheckDeviceFormatFn g_realD3D9CheckDeviceFormat = NULL;
    D3D9CheckDepthStencilMatchFn g_realD3D9CheckDepthStencilMatch = NULL;
    D3D9GetDeviceCapsFn g_realD3D9GetDeviceCaps = NULL;
    D3D9CreateDeviceFn g_realD3D9CreateDevice = NULL;

    DeviceGetDeviceCapsFn g_realDeviceGetDeviceCaps = NULL;
    DeviceResetFn g_realDeviceReset = NULL;
    DevicePresentFn g_realDevicePresent = NULL;
    DeviceCreateRenderTargetFn g_realDeviceCreateRenderTarget = NULL;
    DeviceCreateDepthStencilSurfaceFn g_realDeviceCreateDepthStencilSurface = NULL;
    DeviceSetRenderTargetFn g_realDeviceSetRenderTarget = NULL;
    DeviceSetDepthStencilSurfaceFn g_realDeviceSetDepthStencilSurface = NULL;
    DeviceCreateVertexShaderFn g_realDeviceCreateVertexShader = NULL;
    DeviceSetVertexShaderFn g_realDeviceSetVertexShader = NULL;
    DeviceCreatePixelShaderFn g_realDeviceCreatePixelShader = NULL;
    DeviceSetPixelShaderFn g_realDeviceSetPixelShader = NULL;

    void Log(const char* format, ...)
    {
        char message[1536] = {};
        char line[1792] = {};
        SYSTEMTIME now = {};
        DWORD written = 0;

        va_list args;
        va_start(args, format);
        _vsnprintf_s(message, sizeof(message), _TRUNCATE, format, args);
        va_end(args);

        GetLocalTime(&now);
        _snprintf_s(
            line,
            sizeof(line),
            _TRUNCATE,
            "[%02u:%02u:%02u.%03u] %s\r\n",
            static_cast<unsigned>(now.wHour),
            static_cast<unsigned>(now.wMinute),
            static_cast<unsigned>(now.wSecond),
            static_cast<unsigned>(now.wMilliseconds),
            message);

        while (InterlockedCompareExchange(&g_logLock, 1, 0) != 0)
            Sleep(0);

        if (g_logFile != INVALID_HANDLE_VALUE)
            WriteFile(g_logFile, line, static_cast<DWORD>(strlen(line)), &written, NULL);

        InterlockedExchange(&g_logLock, 0);
        OutputDebugStringA(line);
    }

    bool GetShaderBytecodeInfo(
        const DWORD* function,
        BOOL pixelStage,
        DWORD* versionToken,
        DWORD* byteCount,
        unsigned __int64* hash)
    {
        if (!function || !versionToken || !byteCount || !hash)
            return false;

        bool valid = false;
        __try
        {
            const DWORD version = function[0];
            const DWORD expectedMarker = pixelStage ? 0xFFFF0000UL : 0xFFFE0000UL;
            if ((version & 0xFFFF0000UL) != expectedMarker)
                __leave;

            const DWORD major = (version >> 8) & 0xFF;
            if (major < 2 || major > 3)
                __leave;

            const DWORD maxTokens = 65536;
            DWORD index = 1;
            bool foundEnd = false;

            while (index < maxTokens)
            {
                const DWORD instruction = function[index++];
                const DWORD opcode = instruction & 0xFFFFUL;

                if (opcode == 0xFFFFUL) // D3DSIO_END
                {
                    foundEnd = true;
                    break;
                }

                if (opcode == 0xFFFEUL) // D3DSIO_COMMENT
                {
                    const DWORD commentTokens = (instruction >> 16) & 0x7FFFUL;
                    if (commentTokens > maxTokens - index)
                        __leave;
                    index += commentTokens;
                    continue;
                }

                // For SM2/SM3, the instruction token carries the count of
                // following parameter tokens in bits 24..27.
                const DWORD parameterTokens = (instruction >> 24) & 0x0FUL;
                if (parameterTokens > maxTokens - index)
                    __leave;
                index += parameterTokens;
            }

            if (!foundEnd)
                __leave;

            const DWORD sizeBytes = index * sizeof(DWORD);
            const BYTE* bytes = reinterpret_cast<const BYTE*>(function);
            unsigned __int64 hashValue = 14695981039346656037ULL;
            for (DWORD i = 0; i < sizeBytes; ++i)
            {
                hashValue ^= bytes[i];
                hashValue *= 1099511628211ULL;
            }

            *versionToken = version;
            *byteCount = sizeBytes;
            *hash = hashValue;
            valid = true;
        }
        __except (EXCEPTION_EXECUTE_HANDLER)
        {
            valid = false;
        }

        return valid;
    }

    void CaptureShaderBytecode(const wchar_t* stage, BOOL pixelStage, const DWORD* function)
    {
        if (!g_captureShaderBytecode || !stage || !function)
            return;

        DWORD versionToken = 0;
        DWORD byteCount = 0;
        unsigned __int64 hash = 0;
        if (!GetShaderBytecodeInfo(
            function, pixelStage, &versionToken, &byteCount, &hash))
        {
            return;
        }

        // Reserve a unique-file slot atomically before touching the filesystem.
        // Multiple render/resource threads may create shaders concurrently.
        const LONG reservedSlot = InterlockedIncrement(&g_captureUniqueCount);
        if (reservedSlot > static_cast<LONG>(g_captureMaxFiles))
        {
            InterlockedDecrement(&g_captureUniqueCount);
            return;
        }

        const DWORD major = (versionToken >> 8) & 0xFF;
        const DWORD minor = versionToken & 0xFF;
        wchar_t filePath[MAX_PATH] = {};
        _snwprintf_s(
            filePath,
            MAX_PATH,
            _TRUNCATE,
            L"%s\\%s_%u_%u_%016llX.bin",
            g_captureDirectory,
            stage,
            major,
            minor,
            hash);

        HANDLE file = CreateFileW(
            filePath,
            GENERIC_WRITE,
            FILE_SHARE_READ,
            NULL,
            CREATE_NEW,
            FILE_ATTRIBUTE_NORMAL,
            NULL);

        if (file == INVALID_HANDLE_VALUE)
        {
            const DWORD error = GetLastError();
            InterlockedDecrement(&g_captureUniqueCount);

            // Existing content-addressed capture means this shader was
            // already recorded. Do not log every repeated material use.
            if (error != ERROR_FILE_EXISTS && error != ERROR_ALREADY_EXISTS)
            {
                Log(
                    "SHADER_CAPTURE_FAILED stage=%ls hash=%016llX create_error=%lu",
                    stage, hash, static_cast<unsigned long>(error));
            }
            return;
        }

        DWORD written = 0;
        BOOL writeSucceeded = FALSE;
        __try
        {
            writeSucceeded = WriteFile(file, function, byteCount, &written, NULL);
        }
        __except (EXCEPTION_EXECUTE_HANDLER)
        {
            writeSucceeded = FALSE;
        }

        CloseHandle(file);

        if (!writeSucceeded || written != byteCount)
        {
            DeleteFileW(filePath);
            InterlockedDecrement(&g_captureUniqueCount);
            Log(
                "SHADER_CAPTURE_FAILED stage=%ls hash=%016llX bytes=%lu",
                stage, hash, static_cast<unsigned long>(byteCount));
            return;
        }

        Log(
            "SHADER_CAPTURED stage=%ls profile=%u_%u hash=%016llX bytes=%lu",
            stage,
            major,
            minor,
            hash,
            static_cast<unsigned long>(byteCount));
    }

    bool QueryFileVersion(
        const wchar_t* path,
        DWORD* versionMS,
        DWORD* versionLS)
    {
        DWORD ignored = 0;
        const DWORD size = GetFileVersionInfoSizeW(path, &ignored);
        if (size == 0)
            return false;

        void* data = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, size);
        if (!data)
            return false;

        bool success = false;
        if (GetFileVersionInfoW(path, 0, size, data))
        {
            VS_FIXEDFILEINFO* fixed = NULL;
            UINT fixedSize = 0;
            if (VerQueryValueW(data, L"\\", reinterpret_cast<void**>(&fixed), &fixedSize) &&
                fixed && fixedSize >= sizeof(VS_FIXEDFILEINFO) &&
                fixed->dwSignature == VS_FFI_SIGNATURE)
            {
                *versionMS = fixed->dwFileVersionMS;
                *versionLS = fixed->dwFileVersionLS;
                success = true;
            }
        }

        HeapFree(GetProcessHeap(), 0, data);
        return success;
    }

    bool Is32BitPE(HMODULE module)
    {
        if (!module)
            return false;

        const BYTE* base = reinterpret_cast<const BYTE*>(module);
        const IMAGE_DOS_HEADER* dos =
            reinterpret_cast<const IMAGE_DOS_HEADER*>(base);

        if (dos->e_magic != IMAGE_DOS_SIGNATURE ||
            dos->e_lfanew <= 0 ||
            dos->e_lfanew > 0x100000)
            return false;

        const IMAGE_NT_HEADERS32* nt =
            reinterpret_cast<const IMAGE_NT_HEADERS32*>(base + dos->e_lfanew);

        return nt->Signature == IMAGE_NT_SIGNATURE &&
            nt->FileHeader.Machine == IMAGE_FILE_MACHINE_I386 &&
            nt->OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR32_MAGIC;
    }

    void OpenLogAndPaths()
    {
        DWORD length = GetModuleFileNameW(NULL, g_gamePath, MAX_PATH);
        if (length == 0 || length >= MAX_PATH)
        {
            OutputDebugStringA("[IVLegacy] Could not resolve GTAIV.exe path.\n");
            return;
        }

        wcscpy_s(g_gameDirectory, MAX_PATH, g_gamePath);
        wchar_t* slash = wcsrchr(g_gameDirectory, L'\\');
        if (!slash)
            return;

        *slash = L'\0';
        _snwprintf_s(g_logPath, MAX_PATH, _TRUNCATE, L"%s\\IVLegacy.log", g_gameDirectory);
        _snwprintf_s(g_iniPath, MAX_PATH, _TRUNCATE, L"%s\\IVLegacy.ini", g_gameDirectory);

        g_logFile = CreateFileW(
            g_logPath,
            FILE_APPEND_DATA,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            NULL,
            OPEN_ALWAYS,
            FILE_ATTRIBUTE_NORMAL,
            NULL);

        if (g_logFile == INVALID_HANDLE_VALUE)
            OutputDebugStringA("[IVLegacy] Could not open IVLegacy.log.\n");

        if (GetFileAttributesW(g_iniPath) == INVALID_FILE_ATTRIBUTES)
        {
            WritePrivateProfileStringW(
                L"General", L"EnableD3D9Telemetry", L"1", g_iniPath);
            WritePrivateProfileStringW(
                L"General", L"StrictGTAIV100", L"1", g_iniPath);
            WritePrivateProfileStringW(
                L"General", L"CaptureShaderBytecode", L"0", g_iniPath);
        }
    }

    bool ValidateTargetExecutable(BOOL strictVersion)
    {
        HMODULE exe = GetModuleHandleW(NULL);
        if (!exe || !Is32BitPE(exe))
        {
            Log("TARGET_REJECTED reason=process_is_not_32bit_PE");
            return false;
        }

        const wchar_t* fileName = wcsrchr(g_gamePath, L'\\');
        fileName = fileName ? fileName + 1 : g_gamePath;
        if (_wcsicmp(fileName, L"GTAIV.exe") != 0)
        {
            Log("TARGET_REJECTED reason=unexpected_executable name=%ls", fileName);
            return false;
        }

        DWORD versionMS = 0;
        DWORD versionLS = 0;
        if (!QueryFileVersion(g_gamePath, &versionMS, &versionLS))
        {
            Log("TARGET_REJECTED reason=file_version_resource_unavailable");
            return false;
        }

        const unsigned major = HIWORD(versionMS);
        const unsigned minor = LOWORD(versionMS);
        const unsigned build = HIWORD(versionLS);
        const unsigned revision = LOWORD(versionLS);

        Log(
            "EXECUTABLE path=%ls PE=I386 file_version=%u.%u.%u.%u",
            g_gamePath, major, minor, build, revision);

        if (major != 1 || minor != 0 || build != 0 || revision != 0)
        {
            Log("TARGET_VERSION_MISMATCH expected=1.0.0.0 actual=%u.%u.%u.%u",
                major, minor, build, revision);
            if (strictVersion)
                return false;
            Log("WARNING strict version gate disabled; telemetry-only mode");
            return true;
        }

        Log("TARGET_VERSION_GATE passed=1.0.0.0");
        return true;
    }

    void LogShaderProfile(const char* stage, const DWORD* function, HRESULT result)
    {
        DWORD token = function ? function[0] : 0;
        const unsigned marker = token >> 16;
        const unsigned major = (token >> 8) & 0xff;
        const unsigned minor = token & 0xff;
        const char* tokenStage = marker == 0xFFFF ? "PS" :
            (marker == 0xFFFE ? "VS" : "UNKNOWN");

        if (strcmp(stage, "VS") == 0)
        {
            if (InterlockedIncrement(&g_vertexShaderLogCount) <= 256)
                Log(
                    "CREATE_VERTEX_SHADER profile=%s_%u_%u token=0x%08lX hr=0x%08lX",
                    tokenStage, major, minor, token, static_cast<unsigned long>(result));
        }
        else
        {
            if (InterlockedIncrement(&g_pixelShaderLogCount) <= 512)
                Log(
                    "CREATE_PIXEL_SHADER profile=%s_%u_%u token=0x%08lX hr=0x%08lX",
                    tokenStage, major, minor, token, static_cast<unsigned long>(result));
        }
    }

    HRESULT WINAPI HookD3D9GetDeviceCaps(
        IDirect3D9* self,
        UINT adapter,
        D3DDEVTYPE deviceType,
        D3DCAPS9* caps)
    {
        if (!g_realD3D9GetDeviceCaps)
            return D3DERR_INVALIDCALL;

        const HRESULT hr =
            g_realD3D9GetDeviceCaps(self, adapter, deviceType, caps);

        if (SUCCEEDED(hr) && caps &&
            InterlockedIncrement(&g_capsLogCount) <= 32)
        {
            Log(
                "D3D9_GET_DEVICE_CAPS adapter=%u type=%u VS=0x%08lX PS=0x%08lX "
                "MaxSimTextures=%u MaxTextureStages=%u MaxRTs=%u MaxVSConst=%u "
                "VS20Temps=%u VS20DynamicFlow=%u PS20Temps=%u PS20Slots=%u "
                "PS20DynamicFlow=%u",
                adapter,
                static_cast<unsigned>(deviceType),
                static_cast<unsigned long>(caps->VertexShaderVersion),
                static_cast<unsigned long>(caps->PixelShaderVersion),
                caps->MaxSimultaneousTextures,
                caps->MaxTextureBlendStages,
                caps->NumSimultaneousRTs,
                caps->MaxVertexShaderConst,
                caps->VS20Caps.NumTemps,
                caps->VS20Caps.DynamicFlowControlDepth,
                caps->PS20Caps.NumTemps,
                caps->PS20Caps.NumInstructionSlots,
                caps->PS20Caps.DynamicFlowControlDepth);
        }
        else if (FAILED(hr))
        {
            Log(
                "D3D9_GET_DEVICE_CAPS_FAILED adapter=%u hr=0x%08lX",
                adapter, static_cast<unsigned long>(hr));
        }

        return hr;
    }

    HRESULT WINAPI HookD3D9GetAdapterIdentifier(
        IDirect3D9* self,
        UINT adapter,
        DWORD flags,
        D3DADAPTER_IDENTIFIER9* identifier)
    {
        if (!g_realD3D9GetAdapterIdentifier)
            return D3DERR_INVALIDCALL;

        const HRESULT hr =
            g_realD3D9GetAdapterIdentifier(self, adapter, flags, identifier);
        if (SUCCEEDED(hr) && identifier &&
            InterlockedIncrement(&g_adapterLogCount) <= 16)
        {
            Log(
                "D3D9_ADAPTER adapter=%u vendor=0x%04lX device=0x%04lX "
                "subsys=0x%08lX revision=0x%08lX driver_version=%08lX:%08lX "
                "description=%s driver=%s",
                adapter,
                static_cast<unsigned long>(identifier->VendorId),
                static_cast<unsigned long>(identifier->DeviceId),
                static_cast<unsigned long>(identifier->SubSysId),
                static_cast<unsigned long>(identifier->Revision),
                static_cast<unsigned long>(identifier->DriverVersion.HighPart),
                static_cast<unsigned long>(identifier->DriverVersion.LowPart),
                identifier->Description,
                identifier->Driver);
        }
        else if (FAILED(hr))
        {
            Log(
                "D3D9_ADAPTER_IDENTIFIER_FAILED adapter=%u hr=0x%08lX",
                adapter, static_cast<unsigned long>(hr));
        }
        return hr;
    }

    HRESULT WINAPI HookD3D9CheckDeviceFormat(
        IDirect3D9* self,
        UINT adapter,
        D3DDEVTYPE deviceType,
        D3DFORMAT adapterFormat,
        DWORD usage,
        D3DRESOURCETYPE resourceType,
        D3DFORMAT checkFormat)
    {
        const HRESULT hr = g_realD3D9CheckDeviceFormat
            ? g_realD3D9CheckDeviceFormat(
                self, adapter, deviceType, adapterFormat,
                usage, resourceType, checkFormat)
            : D3DERR_INVALIDCALL;

        if (InterlockedIncrement(&g_formatCheckLogCount) <= 512)
        {
            Log(
                "D3D9_CHECK_DEVICE_FORMAT adapter=%u type=%u adapter_format=%u "
                "usage=0x%08lX resource_type=%u check_format=%u hr=0x%08lX",
                adapter, static_cast<unsigned>(deviceType),
                static_cast<unsigned>(adapterFormat),
                static_cast<unsigned long>(usage),
                static_cast<unsigned>(resourceType),
                static_cast<unsigned>(checkFormat),
                static_cast<unsigned long>(hr));
        }
        return hr;
    }

    HRESULT WINAPI HookD3D9CheckDepthStencilMatch(
        IDirect3D9* self,
        UINT adapter,
        D3DDEVTYPE deviceType,
        D3DFORMAT adapterFormat,
        D3DFORMAT renderTargetFormat,
        D3DFORMAT depthStencilFormat)
    {
        const HRESULT hr = g_realD3D9CheckDepthStencilMatch
            ? g_realD3D9CheckDepthStencilMatch(
                self, adapter, deviceType, adapterFormat,
                renderTargetFormat, depthStencilFormat)
            : D3DERR_INVALIDCALL;

        if (InterlockedIncrement(&g_depthMatchLogCount) <= 256)
        {
            Log(
                "D3D9_CHECK_DEPTH_MATCH adapter=%u type=%u adapter_format=%u "
                "render_format=%u depth_format=%u hr=0x%08lX",
                adapter, static_cast<unsigned>(deviceType),
                static_cast<unsigned>(adapterFormat),
                static_cast<unsigned>(renderTargetFormat),
                static_cast<unsigned>(depthStencilFormat),
                static_cast<unsigned long>(hr));
        }
        return hr;
    }

    HRESULT WINAPI HookDeviceGetDeviceCaps(
        IDirect3DDevice9* self,
        D3DCAPS9* caps)
    {
        if (!g_realDeviceGetDeviceCaps)
            return D3DERR_INVALIDCALL;

        const HRESULT hr = g_realDeviceGetDeviceCaps(self, caps);
        if (SUCCEEDED(hr) && caps)
        {
            Log(
                "DEVICE_GET_DEVICE_CAPS VS=0x%08lX PS=0x%08lX MaxRTs=%u "
                "PS20Temps=%u PS20Slots=%u",
                static_cast<unsigned long>(caps->VertexShaderVersion),
                static_cast<unsigned long>(caps->PixelShaderVersion),
                caps->NumSimultaneousRTs,
                caps->PS20Caps.NumTemps,
                caps->PS20Caps.NumInstructionSlots);
        }
        return hr;
    }

    HRESULT WINAPI HookDeviceReset(
        IDirect3DDevice9* self,
        D3DPRESENT_PARAMETERS* parameters)
    {
        Log(
            "DEVICE_RESET_REQUEST width=%u height=%u format=%u windowed=%u",
            parameters ? parameters->BackBufferWidth : 0,
            parameters ? parameters->BackBufferHeight : 0,
            parameters ? static_cast<unsigned>(parameters->BackBufferFormat) : 0,
            parameters ? parameters->Windowed : 0);

        const HRESULT hr = g_realDeviceReset
            ? g_realDeviceReset(self, parameters)
            : D3DERR_INVALIDCALL;

        Log("DEVICE_RESET_RESULT hr=0x%08lX", static_cast<unsigned long>(hr));
        return hr;
    }

    HRESULT WINAPI HookDevicePresent(
        IDirect3DDevice9* self,
        const RECT* source,
        const RECT* destination,
        HWND overrideWindow,
        const RGNDATA* dirtyRegion)
    {
        const HRESULT hr = g_realDevicePresent
            ? g_realDevicePresent(self, source, destination, overrideWindow, dirtyRegion)
            : D3DERR_INVALIDCALL;

        if (FAILED(hr))
            Log("DEVICE_PRESENT_FAILED hr=0x%08lX", static_cast<unsigned long>(hr));

        return hr;
    }

    HRESULT WINAPI HookDeviceCreateRenderTarget(
        IDirect3DDevice9* self,
        UINT width,
        UINT height,
        D3DFORMAT format,
        D3DMULTISAMPLE_TYPE multisample,
        DWORD quality,
        BOOL lockable,
        IDirect3DSurface9** surface,
        HANDLE* sharedHandle)
    {
        const HRESULT hr = g_realDeviceCreateRenderTarget
            ? g_realDeviceCreateRenderTarget(
                self, width, height, format, multisample,
                quality, lockable, surface, sharedHandle)
            : D3DERR_INVALIDCALL;

        if (InterlockedIncrement(&g_renderTargetLogCount) <= 256)
        {
            Log(
                "CREATE_RENDER_TARGET width=%u height=%u format=%u "
                "multisample=%u quality=%lu lockable=%u hr=0x%08lX",
                width, height, static_cast<unsigned>(format),
                static_cast<unsigned>(multisample),
                static_cast<unsigned long>(quality),
                lockable ? 1 : 0,
                static_cast<unsigned long>(hr));
        }
        return hr;
    }

    HRESULT WINAPI HookDeviceCreateDepthStencilSurface(
        IDirect3DDevice9* self,
        UINT width,
        UINT height,
        D3DFORMAT format,
        D3DMULTISAMPLE_TYPE multisample,
        DWORD quality,
        BOOL discard,
        IDirect3DSurface9** surface,
        HANDLE* sharedHandle)
    {
        const HRESULT hr = g_realDeviceCreateDepthStencilSurface
            ? g_realDeviceCreateDepthStencilSurface(
                self, width, height, format, multisample,
                quality, discard, surface, sharedHandle)
            : D3DERR_INVALIDCALL;

        if (InterlockedIncrement(&g_depthTargetCreateLogCount) <= 256)
        {
            Log(
                "CREATE_DEPTH_STENCIL_SURFACE width=%u height=%u format=%u "
                "multisample=%u quality=%lu discard=%u hr=0x%08lX",
                width, height, static_cast<unsigned>(format),
                static_cast<unsigned>(multisample),
                static_cast<unsigned long>(quality),
                discard ? 1 : 0,
                static_cast<unsigned long>(hr));
        }
        return hr;
    }

    HRESULT WINAPI HookDeviceSetDepthStencilSurface(
        IDirect3DDevice9* self,
        IDirect3DSurface9* surface)
    {
        if (surface && InterlockedIncrement(&g_setDepthTargetLogCount) <= 512)
        {
            D3DSURFACE_DESC desc = {};
            const HRESULT descHr = surface->GetDesc(&desc);
            if (SUCCEEDED(descHr))
            {
                Log(
                    "SET_DEPTH_STENCIL_SURFACE width=%u height=%u format=%u",
                    desc.Width, desc.Height, static_cast<unsigned>(desc.Format));
            }
            else
            {
                Log("SET_DEPTH_STENCIL_SURFACE desc_hr=0x%08lX",
                    static_cast<unsigned long>(descHr));
            }
        }

        return g_realDeviceSetDepthStencilSurface
            ? g_realDeviceSetDepthStencilSurface(self, surface)
            : D3DERR_INVALIDCALL;
    }

    HRESULT WINAPI HookDeviceSetRenderTarget(
        IDirect3DDevice9* self,
        DWORD index,
        IDirect3DSurface9* surface)
    {
        if (InterlockedIncrement(&g_setRenderTargetLogCount) <= 512)
        {
            if (surface)
            {
                D3DSURFACE_DESC desc = {};
                const HRESULT descHr = surface->GetDesc(&desc);
                if (SUCCEEDED(descHr))
                {
                    Log(
                        "SET_RENDER_TARGET index=%lu width=%u height=%u "
                        "format=%u type=%u",
                        static_cast<unsigned long>(index),
                        desc.Width, desc.Height,
                        static_cast<unsigned>(desc.Format),
                        static_cast<unsigned>(desc.Type));
                }
                else
                {
                    Log(
                        "SET_RENDER_TARGET index=%lu desc_hr=0x%08lX",
                        static_cast<unsigned long>(index),
                        static_cast<unsigned long>(descHr));
                }
            }
            else
            {
                Log("SET_RENDER_TARGET index=%lu surface=NULL",
                    static_cast<unsigned long>(index));
            }
        }

        return g_realDeviceSetRenderTarget
            ? g_realDeviceSetRenderTarget(self, index, surface)
            : D3DERR_INVALIDCALL;
    }

    HRESULT WINAPI HookDeviceCreateVertexShader(
        IDirect3DDevice9* self,
        const DWORD* function,
        IDirect3DVertexShader9** shader)
    {
        const HRESULT hr = g_realDeviceCreateVertexShader
            ? g_realDeviceCreateVertexShader(self, function, shader)
            : D3DERR_INVALIDCALL;
        LogShaderProfile("VS", function, hr);
        CaptureShaderBytecode(L"VS", FALSE, function);
        return hr;
    }

    HRESULT WINAPI HookDeviceCreatePixelShader(
        IDirect3DDevice9* self,
        const DWORD* function,
        IDirect3DPixelShader9** shader)
    {
        const HRESULT hr = g_realDeviceCreatePixelShader
            ? g_realDeviceCreatePixelShader(self, function, shader)
            : D3DERR_INVALIDCALL;
        LogShaderProfile("PS", function, hr);
        CaptureShaderBytecode(L"PS", TRUE, function);
        return hr;
    }

    HRESULT WINAPI HookDeviceSetVertexShader(
        IDirect3DDevice9* self,
        IDirect3DVertexShader9* shader)
    {
        const HRESULT hr = g_realDeviceSetVertexShader
            ? g_realDeviceSetVertexShader(self, shader)
            : D3DERR_INVALIDCALL;

        if (InterlockedIncrement(&g_setVertexShaderLogCount) <= 2048)
        {
            Log(
                "SET_VERTEX_SHADER object=%p hr=0x%08lX",
                shader, static_cast<unsigned long>(hr));
        }
        return hr;
    }

    HRESULT WINAPI HookDeviceSetPixelShader(
        IDirect3DDevice9* self,
        IDirect3DPixelShader9* shader)
    {
        const HRESULT hr = g_realDeviceSetPixelShader
            ? g_realDeviceSetPixelShader(self, shader)
            : D3DERR_INVALIDCALL;

        if (InterlockedIncrement(&g_setPixelShaderLogCount) <= 2048)
        {
            Log(
                "SET_PIXEL_SHADER object=%p hr=0x%08lX",
                shader, static_cast<unsigned long>(hr));
        }
        return hr;
    }

    bool HookD3D9Device(IDirect3DDevice9* device)
    {
        if (!device)
            return false;

        void*** objectVTable = reinterpret_cast<void***>(device);
        if (!objectVTable || !*objectVTable)
            return false;

        void** original = *objectVTable;
        Log("D3D9_DEVICE_HOOK_BEGIN device=%p vtable=%p", device, original);
        if (original[kDeviceGetDeviceCapsSlot] == reinterpret_cast<void*>(HookDeviceGetDeviceCaps))
            return true;

        const SIZE_T vtableBytes =
            sizeof(void*) * kD3D9DeviceInterfaceSlots;
        MEMORY_BASIC_INFORMATION vtableMemory = {};
        if (VirtualQuery(original, &vtableMemory, sizeof(vtableMemory)) != sizeof(vtableMemory) ||
            vtableMemory.State != MEM_COMMIT ||
            (vtableMemory.Protect & (PAGE_NOACCESS | PAGE_GUARD)) != 0)
        {
            Log("D3D9_DEVICE_HOOK_FAILED reason=invalid_vtable_memory");
            return false;
        }

        const BYTE* vtableEnd =
            static_cast<const BYTE*>(vtableMemory.BaseAddress) + vtableMemory.RegionSize;
        if (reinterpret_cast<const BYTE*>(original) + vtableBytes > vtableEnd)
        {
            Log("D3D9_DEVICE_HOOK_FAILED reason=vtable_region_too_small required=%lu",
                static_cast<unsigned long>(vtableBytes));
            return false;
        }

        void** hooked = static_cast<void**>(
            HeapAlloc(GetProcessHeap(), 0, vtableBytes));
        if (!hooked)
        {
            Log("D3D9_DEVICE_HOOK_FAILED reason=out_of_memory");
            return false;
        }

        CopyMemory(hooked, original, vtableBytes);
        Log("D3D9_DEVICE_VTABLE_COPIED bytes=%lu", static_cast<unsigned long>(vtableBytes));

        g_realDeviceGetDeviceCaps =
            reinterpret_cast<DeviceGetDeviceCapsFn>(original[kDeviceGetDeviceCapsSlot]);
        g_realDeviceReset = reinterpret_cast<DeviceResetFn>(original[kDeviceResetSlot]);
        g_realDevicePresent = reinterpret_cast<DevicePresentFn>(original[kDevicePresentSlot]);
        g_realDeviceCreateRenderTarget =
            reinterpret_cast<DeviceCreateRenderTargetFn>(original[kDeviceCreateRenderTargetSlot]);
        g_realDeviceCreateDepthStencilSurface =
            reinterpret_cast<DeviceCreateDepthStencilSurfaceFn>(original[kDeviceCreateDepthStencilSurfaceSlot]);
        g_realDeviceSetRenderTarget =
            reinterpret_cast<DeviceSetRenderTargetFn>(original[kDeviceSetRenderTargetSlot]);
        g_realDeviceSetDepthStencilSurface =
            reinterpret_cast<DeviceSetDepthStencilSurfaceFn>(original[kDeviceSetDepthStencilSurfaceSlot]);
        g_realDeviceCreateVertexShader =
            reinterpret_cast<DeviceCreateVertexShaderFn>(original[kDeviceCreateVertexShaderSlot]);
        g_realDeviceCreatePixelShader =
            reinterpret_cast<DeviceCreatePixelShaderFn>(original[kDeviceCreatePixelShaderSlot]);
        g_realDeviceSetVertexShader =
            reinterpret_cast<DeviceSetVertexShaderFn>(original[kDeviceSetVertexShaderSlot]);
        g_realDeviceSetPixelShader =
            reinterpret_cast<DeviceSetPixelShaderFn>(original[kDeviceSetPixelShaderSlot]);

        hooked[kDeviceGetDeviceCapsSlot] = reinterpret_cast<void*>(HookDeviceGetDeviceCaps);
        hooked[kDeviceResetSlot] = reinterpret_cast<void*>(HookDeviceReset);
        hooked[kDevicePresentSlot] = reinterpret_cast<void*>(HookDevicePresent);
        hooked[kDeviceCreateRenderTargetSlot] = reinterpret_cast<void*>(HookDeviceCreateRenderTarget);
        hooked[kDeviceCreateDepthStencilSurfaceSlot] = reinterpret_cast<void*>(HookDeviceCreateDepthStencilSurface);
        hooked[kDeviceSetRenderTargetSlot] = reinterpret_cast<void*>(HookDeviceSetRenderTarget);
        hooked[kDeviceSetDepthStencilSurfaceSlot] = reinterpret_cast<void*>(HookDeviceSetDepthStencilSurface);
        hooked[kDeviceCreateVertexShaderSlot] = reinterpret_cast<void*>(HookDeviceCreateVertexShader);
        hooked[kDeviceCreatePixelShaderSlot] = reinterpret_cast<void*>(HookDeviceCreatePixelShader);
        hooked[kDeviceSetVertexShaderSlot] = reinterpret_cast<void*>(HookDeviceSetVertexShader);
        hooked[kDeviceSetPixelShaderSlot] = reinterpret_cast<void*>(HookDeviceSetPixelShader);

        DWORD oldProtection = 0;
        if (!VirtualProtect(objectVTable, sizeof(void*), PAGE_READWRITE, &oldProtection))
        {
            HeapFree(GetProcessHeap(), 0, hooked);
            Log("D3D9_DEVICE_HOOK_FAILED reason=vtable_pointer_protect");
            return false;
        }

        *objectVTable = hooked;
        DWORD ignored = 0;
        const BOOL restoreProtection =
            VirtualProtect(objectVTable, sizeof(void*), oldProtection, &ignored);
        FlushInstructionCache(GetCurrentProcess(), NULL, 0);

        Log(
            "D3D9_DEVICE_HOOK_INSTALLED device=%p vtable=%p restore_protection=%u",
            device, hooked, restoreProtection ? 1 : 0);
        return true;
    }

    HRESULT WINAPI HookD3D9CreateDevice(
        IDirect3D9* self,
        UINT adapter,
        D3DDEVTYPE deviceType,
        HWND focusWindow,
        DWORD behaviorFlags,
        D3DPRESENT_PARAMETERS* parameters,
        IDirect3DDevice9** device)
    {
        Log(
            "D3D9_CREATE_DEVICE_REQUEST adapter=%u type=%u flags=0x%08lX "
            "width=%u height=%u backbuffer_format=%u windowed=%u",
            adapter,
            static_cast<unsigned>(deviceType),
            static_cast<unsigned long>(behaviorFlags),
            parameters ? parameters->BackBufferWidth : 0,
            parameters ? parameters->BackBufferHeight : 0,
            parameters ? static_cast<unsigned>(parameters->BackBufferFormat) : 0,
            parameters ? parameters->Windowed : 0);

        const HRESULT hr = g_realD3D9CreateDevice
            ? g_realD3D9CreateDevice(
                self, adapter, deviceType, focusWindow,
                behaviorFlags, parameters, device)
            : D3DERR_INVALIDCALL;

        Log("D3D9_CREATE_DEVICE_RESULT hr=0x%08lX", static_cast<unsigned long>(hr));
        if (SUCCEEDED(hr) && device && *device)
            HookD3D9Device(*device);

        return hr;
    }

    IDirect3D9* WINAPI HookDirect3DCreate9(UINT sdkVersion)
    {
        IDirect3D9* d3d = g_realDirect3DCreate9
            ? g_realDirect3DCreate9(sdkVersion)
            : NULL;

        Log("DIRECT3DCREATE9 sdk=%u result=%p", sdkVersion, d3d);
        if (!d3d)
            return NULL;

        void*** objectVTable = reinterpret_cast<void***>(d3d);
        if (!objectVTable || !*objectVTable)
            return d3d;

        void** original = *objectVTable;
        if (original[kD3D9CreateDeviceSlot] == reinterpret_cast<void*>(HookD3D9CreateDevice))
            return d3d;

        void** hooked = static_cast<void**>(
            HeapAlloc(GetProcessHeap(), 0, sizeof(void*) * kD3D9InterfaceSlots));
        if (!hooked)
        {
            Log("D3D9_INTERFACE_HOOK_FAILED reason=out_of_memory");
            return d3d;
        }

        CopyMemory(hooked, original, sizeof(void*) * kD3D9InterfaceSlots);
        g_realD3D9GetAdapterIdentifier =
            reinterpret_cast<D3D9GetAdapterIdentifierFn>(original[kD3D9GetAdapterIdentifierSlot]);
        g_realD3D9CheckDeviceFormat =
            reinterpret_cast<D3D9CheckDeviceFormatFn>(original[kD3D9CheckDeviceFormatSlot]);
        g_realD3D9CheckDepthStencilMatch =
            reinterpret_cast<D3D9CheckDepthStencilMatchFn>(original[kD3D9CheckDepthStencilMatchSlot]);
        g_realD3D9GetDeviceCaps =
            reinterpret_cast<D3D9GetDeviceCapsFn>(original[kD3D9GetDeviceCapsSlot]);
        g_realD3D9CreateDevice =
            reinterpret_cast<D3D9CreateDeviceFn>(original[kD3D9CreateDeviceSlot]);

        hooked[kD3D9GetAdapterIdentifierSlot] = reinterpret_cast<void*>(HookD3D9GetAdapterIdentifier);
        hooked[kD3D9CheckDeviceFormatSlot] = reinterpret_cast<void*>(HookD3D9CheckDeviceFormat);
        hooked[kD3D9CheckDepthStencilMatchSlot] = reinterpret_cast<void*>(HookD3D9CheckDepthStencilMatch);
        hooked[kD3D9GetDeviceCapsSlot] = reinterpret_cast<void*>(HookD3D9GetDeviceCaps);
        hooked[kD3D9CreateDeviceSlot] = reinterpret_cast<void*>(HookD3D9CreateDevice);

        DWORD oldProtection = 0;
        if (!VirtualProtect(objectVTable, sizeof(void*), PAGE_READWRITE, &oldProtection))
        {
            HeapFree(GetProcessHeap(), 0, hooked);
            Log("D3D9_INTERFACE_HOOK_FAILED reason=vtable_pointer_protect");
            return d3d;
        }

        *objectVTable = hooked;
        DWORD ignored = 0;
        VirtualProtect(objectVTable, sizeof(void*), oldProtection, &ignored);
        FlushInstructionCache(GetCurrentProcess(), NULL, 0);

        Log("D3D9_INTERFACE_HOOK_INSTALLED interface=%p", d3d);
        return d3d;
    }

    bool HookD3D9Import()
    {
        HMODULE exe = GetModuleHandleW(NULL);
        if (!exe || !Is32BitPE(exe))
            return false;

        BYTE* base = reinterpret_cast<BYTE*>(exe);
        IMAGE_DOS_HEADER* dos = reinterpret_cast<IMAGE_DOS_HEADER*>(base);
        IMAGE_NT_HEADERS32* nt =
            reinterpret_cast<IMAGE_NT_HEADERS32*>(base + dos->e_lfanew);

        const IMAGE_DATA_DIRECTORY importDirectory =
            nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
        if (importDirectory.VirtualAddress == 0)
        {
            Log("D3D9_IAT_HOOK_NOT_INSTALLED reason=no_import_directory");
            return false;
        }

        IMAGE_IMPORT_DESCRIPTOR* descriptor =
            reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(
                base + importDirectory.VirtualAddress);

        bool foundD3D9 = false;
        bool installed = false;

        for (; descriptor->Name != 0; ++descriptor)
        {
            const char* moduleName =
                reinterpret_cast<const char*>(base + descriptor->Name);

            if (_stricmp(moduleName, "d3d9.dll") != 0)
                continue;

            foundD3D9 = true;
            if (descriptor->OriginalFirstThunk == 0)
            {
                Log("D3D9_IAT_HOOK_SKIPPED reason=no_original_thunk");
                continue;
            }

            IMAGE_THUNK_DATA32* names =
                reinterpret_cast<IMAGE_THUNK_DATA32*>(
                    base + descriptor->OriginalFirstThunk);
            IMAGE_THUNK_DATA32* addresses =
                reinterpret_cast<IMAGE_THUNK_DATA32*>(
                    base + descriptor->FirstThunk);

            for (; names->u1.AddressOfData != 0; ++names, ++addresses)
            {
                if (IMAGE_SNAP_BY_ORDINAL32(names->u1.Ordinal))
                    continue;

                IMAGE_IMPORT_BY_NAME* importByName =
                    reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(
                        base + names->u1.AddressOfData);

                if (strcmp(
                    reinterpret_cast<const char*>(importByName->Name),
                    "Direct3DCreate9") != 0)
                    continue;

                void* current = reinterpret_cast<void*>(
                    static_cast<ULONG_PTR>(addresses->u1.Function));
                if (current == reinterpret_cast<void*>(HookDirect3DCreate9))
                {
                    installed = true;
                    continue;
                }

                g_realDirect3DCreate9 =
                    reinterpret_cast<Direct3DCreate9Fn>(current);

                DWORD oldProtection = 0;
                if (!VirtualProtect(
                    &addresses->u1.Function,
                    sizeof(addresses->u1.Function),
                    PAGE_READWRITE,
                    &oldProtection))
                {
                    Log("D3D9_IAT_HOOK_FAILED reason=iat_protect");
                    continue;
                }

                InterlockedExchange(
                    reinterpret_cast<volatile LONG*>(&addresses->u1.Function),
                    static_cast<LONG>(
                        reinterpret_cast<ULONG_PTR>(HookDirect3DCreate9)));

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

                installed = true;
                Log(
                    "D3D9_IAT_HOOK_INSTALLED original=%p replacement=%p",
                    current, reinterpret_cast<void*>(HookDirect3DCreate9));
            }
        }

        if (!foundD3D9)
            Log("D3D9_IAT_HOOK_NOT_INSTALLED reason=d3d9_import_not_found");
        else if (!installed)
            Log("D3D9_IAT_HOOK_NOT_INSTALLED reason=direct3dcreate9_not_patched");

        return installed;
    }

    DWORD WINAPI BootstrapThread(void*)
    {
        OpenLogAndPaths();
        Log("IV LEGACY SHADER ENGINE instrumentation build starting");
        Log("PROCESS pointer_size=%u", static_cast<unsigned>(sizeof(void*)));

        g_telemetryEnabled =
            GetPrivateProfileIntW(
                L"General", L"EnableD3D9Telemetry", 1, g_iniPath) != 0;

        g_captureShaderBytecode =
            GetPrivateProfileIntW(
                L"General", L"CaptureShaderBytecode", 0, g_iniPath) != 0;
        g_captureMaxFiles = GetPrivateProfileIntW(
            L"General", L"CaptureMaxFiles", 1024, g_iniPath);
        if (g_captureMaxFiles == 0)
            g_captureMaxFiles = 1;
        if (g_captureMaxFiles > 4096)
            g_captureMaxFiles = 4096;

        if (g_captureShaderBytecode)
        {
            _snwprintf_s(
                g_captureDirectory,
                MAX_PATH,
                _TRUNCATE,
                L"%s\\IVLegacyCaptures",
                g_gameDirectory);
            if (CreateDirectoryW(g_captureDirectory, NULL) ||
                GetLastError() == ERROR_ALREADY_EXISTS)
            {
                Log(
                    "SHADER_CAPTURE_ENABLED directory=IVLegacyCaptures max_files=%lu",
                    static_cast<unsigned long>(g_captureMaxFiles));
            }
            else
            {
                g_captureShaderBytecode = FALSE;
                Log("SHADER_CAPTURE_DISABLED reason=cannot_create_capture_directory");
            }
        }

        const BOOL strictVersion =
            GetPrivateProfileIntW(
                L"General", L"StrictGTAIV100", 1, g_iniPath) != 0;

        if (!ValidateTargetExecutable(strictVersion))
        {
            Log("BOOTSTRAP_STOP reason=target_validation_failed");
            return 0;
        }

        if (!strictVersion)
            Log("WARNING non-1.0.0.0 executable may use different runtime behavior; telemetry only");

        if (!g_telemetryEnabled)
        {
            Log("BOOTSTRAP_STOP reason=telemetry_disabled_in_ini");
            return 0;
        }

        if (!HookD3D9Import())
            Log("BOOTSTRAP_WARNING D3D9 import hook could not be installed");

        Log(
            "BOOTSTRAP_COMPLETE target=GTAIV_1.0.0.0 telemetry=%u",
            g_telemetryEnabled ? 1 : 0);
        return 0;
    }

    void InitializePluginOnce()
    {
        if (InterlockedCompareExchange(&g_bootstrapStarted, 1, 0) == 0)
        {
            BootstrapThread(NULL);
            InterlockedExchange(&g_bootstrapCompleted, 1);
            return;
        }

        // Ultimate ASI Loader calls InitializeASI immediately after LoadLibrary.
        // Another loader may already have started the DllMain fallback worker.
        while (InterlockedCompareExchange(&g_bootstrapCompleted, 0, 0) == 0)
            Sleep(0);
    }

    DWORD WINAPI BootstrapWorkerThread(void*)
    {
        InitializePluginOnce();
        return 0;
    }
}

extern "C" void InitializeASI()
{
    // Official Ultimate ASI Loader entry point; called outside the loader lock.
    InitializePluginOnce();
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(instance);

        // Compatibility fallback for ASI loaders that only call LoadLibrary.
        // Keep DllMain limited to creating the worker; initialization runs later.
        HANDLE thread = CreateThread(NULL, 0, BootstrapWorkerThread, NULL, 0, NULL);
        if (thread)
            CloseHandle(thread);
        else
            OutputDebugStringA("[IVLegacy] Failed to create bootstrap thread.\n");
    }

    return TRUE;
}
