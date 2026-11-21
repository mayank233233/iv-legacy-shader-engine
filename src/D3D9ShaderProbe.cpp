#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d9.h>
#if defined(_WIN64) || !defined(_M_IX86)
#error Build this probe with the 32-bit x86 MSVC toolchain.
#endif
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

static HWND g_window = NULL;
static bool g_quit = false;
static const DWORD kClearColor = D3DCOLOR_XRGB(24, 24, 32);

static LRESULT CALLBACK WindowProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WM_CLOSE) { DestroyWindow(hwnd); return 0; }
    if (msg == WM_DESTROY) { g_quit = true; PostQuitMessage(0); return 0; }
    return DefWindowProc(hwnd, msg, wp, lp);
}

static std::string Hr(HRESULT hr)
{
    char b[32];
    std::snprintf(b, sizeof(b), "0x%08lX", static_cast<unsigned long>(hr));
    return b;
}

static void Log(std::ofstream& file, const std::string& s)
{
    std::cout << s << std::endl;
    file << s << "\r\n";
    file.flush();
}

static bool LoadBytecode(const char* path, DWORD expectedVersion,
                         std::vector<DWORD>& code, std::ofstream& report)
{
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    if (!in) {
        Log(report, std::string("LOAD_FAIL ") + path + " (file not found)");
        return false;
    }
    const std::streamoff size = in.tellg();
    if (size < 8 || (size % 4) != 0) {
        Log(report, std::string("LOAD_FAIL ") + path + " (invalid bytecode length)");
        return false;
    }
    in.seekg(0, std::ios::beg);
    code.resize(static_cast<size_t>(size / 4));
    in.read(reinterpret_cast<char*>(code.data()), size);
    if (!in || code.empty()) {
        Log(report, std::string("LOAD_FAIL ") + path + " (read error)");
        return false;
    }
    if (code[0] != expectedVersion) {
        Log(report, std::string("PROFILE_FAIL ") + path + " expected=" + Hr(expectedVersion) +
                    " actual=" + Hr(code[0]));
        return false;
    }
    if (code.back() != 0x0000FFFFu) {
        Log(report, std::string("BYTECODE_END_FAIL ") + path + " (missing D3DSIO_END token)");
        return false;
    }
    Log(report, std::string("LOAD_OK ") + path + " bytes=" + std::to_string(static_cast<long long>(size)));
    return true;
}

struct Vertex
{
    float x, y, z;
    float nx, ny, nz;
    float u, v;
    DWORD color;
};

// Varying Z is intentional: it drives a visible fog gradient through the VS.
static const Vertex kQuad[4] = {
    {-0.80f, -0.80f, 0.20f,  0.20f, 0.10f, -1.0f, 0.0f, 1.0f, 0xFFFF6040},
    {-0.80f,  0.80f, 0.70f,  0.10f, 0.20f, -1.0f, 0.0f, 0.0f, 0xFF40C060},
    { 0.80f, -0.80f, 0.35f, -0.10f, 0.15f, -1.0f, 1.0f, 1.0f, 0xFF4080FF},
    { 0.80f,  0.80f, 0.80f, -0.15f, 0.05f, -1.0f, 1.0f, 0.0f, 0xFFFFFF40}
};

static const D3DVERTEXELEMENT9 kBasicDecl[] = {
    {0, static_cast<WORD>(offsetof(Vertex, x)),  D3DDECLTYPE_FLOAT3, D3DDECLMETHOD_DEFAULT, D3DDECLUSAGE_POSITION, 0},
    {0, static_cast<WORD>(offsetof(Vertex, nx)), D3DDECLTYPE_FLOAT3, D3DDECLMETHOD_DEFAULT, D3DDECLUSAGE_NORMAL, 0},
    {0, static_cast<WORD>(offsetof(Vertex, u)),  D3DDECLTYPE_FLOAT2, D3DDECLMETHOD_DEFAULT, D3DDECLUSAGE_TEXCOORD, 0},
    D3DDECL_END()
};
static const D3DVERTEXELEMENT9 kFlatDecl[] = {
    {0, static_cast<WORD>(offsetof(Vertex, x)),     D3DDECLTYPE_FLOAT3, D3DDECLMETHOD_DEFAULT, D3DDECLUSAGE_POSITION, 0},
    {0, static_cast<WORD>(offsetof(Vertex, color)), D3DDECLTYPE_D3DCOLOR, D3DDECLMETHOD_DEFAULT, D3DDECLUSAGE_COLOR, 0},
    D3DDECL_END()
};

static bool MakePatternTexture(IDirect3DDevice9* dev, bool secondPattern,
                               IDirect3DTexture9** out, std::ofstream& report)
{
    *out = NULL;
    HRESULT hr = dev->CreateTexture(4, 4, 1, 0, D3DFMT_A8R8G8B8, D3DPOOL_MANAGED, out, NULL);
    if (FAILED(hr)) {
        Log(report, std::string("TEXTURE_CREATE_FAIL ") + Hr(hr));
        return false;
    }

    static const DWORD pattern0[16] = {
        0xFFFF6040, 0xFF40C060, 0xFFFFD040, 0xFF4080FF,
        0xFF40C060, 0xFFFF6040, 0xFF4080FF, 0xFFFFD040,
        0xFFFFD040, 0xFF4080FF, 0xFFFF6040, 0xFF40C060,
        0xFF4080FF, 0xFFFFD040, 0xFF40C060, 0xFFFF6040
    };
    static const DWORD pattern1[16] = {
        0xA060D8FF, 0xD04080E0, 0x8060C0FF, 0xE030A0D0,
        0xD04080E0, 0x8060C0FF, 0xE030A0D0, 0xA060D8FF,
        0x8060C0FF, 0xE030A0D0, 0xA060D8FF, 0xD04080E0,
        0xE030A0D0, 0xA060D8FF, 0xD04080E0, 0x8060C0FF
    };

    D3DLOCKED_RECT lock = {};
    hr = (*out)->LockRect(0, &lock, NULL, 0);
    if (FAILED(hr)) {
        Log(report, std::string("TEXTURE_LOCK_FAIL ") + Hr(hr));
        (*out)->Release();
        *out = NULL;
        return false;
    }
    for (int y = 0; y < 4; ++y) {
        DWORD* row = reinterpret_cast<DWORD*>(static_cast<BYTE*>(lock.pBits) + y * lock.Pitch);
        for (int x = 0; x < 4; ++x) {
            const int index = y * 4 + x;
            row[x] = secondPattern ? pattern1[index] : pattern0[index];
        }
    }
    hr = (*out)->UnlockRect(0);
    if (FAILED(hr)) {
        Log(report, std::string("TEXTURE_UNLOCK_FAIL ") + Hr(hr));
        (*out)->Release();
        *out = NULL;
        return false;
    }
    return true;
}

static bool ReadCenterPixel(IDirect3DDevice9* dev, std::string& detail,
                            bool& pixelChanged, std::ofstream& report)
{
    pixelChanged = false;
    IDirect3DSurface9* back = NULL;
    IDirect3DSurface9* system = NULL;
    HRESULT hr = dev->GetRenderTarget(0, &back);
    if (FAILED(hr)) { detail = "GET_RT_FAIL " + Hr(hr); return false; }

    D3DSURFACE_DESC desc = {};
    hr = back->GetDesc(&desc);
    if (FAILED(hr)) {
        back->Release();
        detail = "RT_DESC_FAIL " + Hr(hr);
        return false;
    }
    if (desc.Format != D3DFMT_X8R8G8B8 && desc.Format != D3DFMT_A8R8G8B8) {
        back->Release();
        detail = "READBACK_UNSUPPORTED_FORMAT=" + std::to_string(static_cast<unsigned>(desc.Format));
        return false;
    }

    hr = dev->CreateOffscreenPlainSurface(desc.Width, desc.Height, desc.Format,
                                          D3DPOOL_SYSTEMMEM, &system, NULL);
    if (FAILED(hr)) {
        back->Release();
        detail = "READBACK_SURFACE_FAIL " + Hr(hr);
        return false;
    }
    hr = dev->GetRenderTargetData(back, system);
    back->Release();
    if (FAILED(hr)) {
        system->Release();
        detail = "READBACK_FAIL " + Hr(hr);
        return false;
    }

    D3DLOCKED_RECT lock = {};
    hr = system->LockRect(&lock, NULL, D3DLOCK_READONLY);
    if (FAILED(hr)) {
        system->Release();
        detail = "READBACK_LOCK_FAIL " + Hr(hr);
        return false;
    }
    const int x = static_cast<int>(desc.Width / 2);
    const int y = static_cast<int>(desc.Height / 2);
    const DWORD pixel = *reinterpret_cast<const DWORD*>(
        static_cast<const BYTE*>(lock.pBits) + y * lock.Pitch + x * 4);
    const HRESULT unlockHr = system->UnlockRect();
    system->Release();
    if (FAILED(unlockHr)) {
        detail = "READBACK_UNLOCK_FAIL " + Hr(unlockHr);
        Log(report, detail);
        return false;
    }

    pixelChanged = (pixel & 0x00FFFFFFu) != (kClearColor & 0x00FFFFFFu);
    char b[96];
    std::snprintf(b, sizeof(b), "CENTER_PIXEL=0x%08lX PIXEL_CHANGED=%s",
        static_cast<unsigned long>(pixel), pixelChanged ? "YES" : "NO");
    detail = b;
    return true;
}

static bool CheckRenderCall(HRESULT hr, const char* operation, const char* testName,
                            std::ofstream& report)
{
    if (FAILED(hr)) {
        Log(report, std::string(testName) + " " + operation + "_FAIL " + Hr(hr));
        return false;
    }
    return true;
}

static void SetBasicVertexConstants(IDirect3DDevice9* dev, const char* testName,
                                    std::ofstream& report, bool& ok)
{
    // Row-major matrices for row-vector mul(vector, matrix). These are intentionally
    // non-identity and include non-uniform world scale plus its inverse-transpose.
    // WVP is World * View * Projection for the matrices represented here.
    const float wvp[16] = {
        0.945f, 0, 0, 0,
        0, 0.765f, 0, 0,
        0, 0, 0.55f, 0,
        0.023f, 0.00f, 0.1825f, 1
    };
    const float world[16] = {
        1.05f, 0, 0, 0,
        0, 0.85f, 0, 0,
        0, 0, 1.00f, 0,
        0, 0, 0, 1
    };
    const float inverseTranspose[16] = {
        0.95238096f, 0, 0, 0,
        0, 1.17647059f, 0, 0,
        0, 0, 1.00f, 0,
        0, 0, 0, 1
    };
    const float view[16] = {
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0.15f, 1
    };
    const float ambient[4] = {0.42f, 0.42f, 0.42f, 1.0f};
    const float diffuse[4] = {0.55f, 0.55f, 0.55f, 1.0f};
    const float light[4] = {0.25f, 0.15f, -1.0f, 0.0f};
    const float fog[4] = {2.0f, 0.5f, 0.0f, 0.0f};

#define SET_VS_CONSTANT(start, data, count, label) do { \
    if (!CheckRenderCall(dev->SetVertexShaderConstantF((start), (data), (count)), (label), testName, report)) ok = false; \
} while (0)
    SET_VS_CONSTANT(0, wvp, 4, "WVP_CONSTANTS");
    SET_VS_CONSTANT(4, world, 4, "WORLD_CONSTANTS");
    SET_VS_CONSTANT(8, inverseTranspose, 4, "NORMAL_MATRIX_CONSTANTS");
    SET_VS_CONSTANT(12, view, 4, "VIEW_CONSTANTS");
    SET_VS_CONSTANT(16, ambient, 1, "AMBIENT_CONSTANT");
    SET_VS_CONSTANT(17, diffuse, 1, "DIFFUSE_CONSTANT");
    SET_VS_CONSTANT(18, light, 1, "LIGHT_CONSTANT");
    SET_VS_CONSTANT(19, fog, 1, "FOG_CONSTANT");
#undef SET_VS_CONSTANT
}

static bool RenderCase(IDirect3DDevice9* dev, IDirect3DVertexDeclaration9* basicDecl,
                       IDirect3DVertexDeclaration9* flatDecl,
                       IDirect3DVertexShader9* basicVS, IDirect3DVertexShader9* flatVS,
                       IDirect3DPixelShader9* ps, IDirect3DTexture9* tex0,
                       IDirect3DTexture9* tex1, const char* name,
                       int kind, bool alphaBlend, std::ofstream& report,
                       bool& readbackAvailable, bool& pixelChanged)
{
    readbackAvailable = false;
    pixelChanged = false;
    HRESULT hr = dev->Clear(0, NULL, D3DCLEAR_TARGET, kClearColor, 1.0f, 0);
    if (FAILED(hr)) { Log(report, std::string(name) + " CLEAR_FAIL " + Hr(hr)); return false; }
    hr = dev->BeginScene();
    if (FAILED(hr)) { Log(report, std::string(name) + " BEGINSCENE_FAIL " + Hr(hr)); return false; }

#define CHECK_STATE(label, expression) do { \
    if (!CheckRenderCall((expression), (label), name, report)) { \
        const HRESULT endFailureHr = dev->EndScene(); \
        if (FAILED(endFailureHr)) Log(report, std::string(name) + " ENDSCENE_AFTER_STATE_FAIL " + Hr(endFailureHr)); \
        return false; \
    } \
} while (0)
    CHECK_STATE("ZENABLE", dev->SetRenderState(D3DRS_ZENABLE, FALSE));
    CHECK_STATE("CULLMODE", dev->SetRenderState(D3DRS_CULLMODE, D3DCULL_NONE));
    CHECK_STATE("LIGHTING", dev->SetRenderState(D3DRS_LIGHTING, FALSE));
    CHECK_STATE("ALPHABLEND", dev->SetRenderState(D3DRS_ALPHABLENDENABLE, alphaBlend ? TRUE : FALSE));
    CHECK_STATE("SRCBLEND", dev->SetRenderState(D3DRS_SRCBLEND, D3DBLEND_SRCALPHA));
    CHECK_STATE("DESTBLEND", dev->SetRenderState(D3DRS_DESTBLEND, D3DBLEND_INVSRCALPHA));
    CHECK_STATE("BLENDOP", dev->SetRenderState(D3DRS_BLENDOP, D3DBLENDOP_ADD));
    CHECK_STATE("VERTEX_SHADER_BIND", dev->SetVertexShader(kind == 3 ? flatVS : basicVS));
    CHECK_STATE("PIXEL_SHADER_BIND", dev->SetPixelShader(ps));
    CHECK_STATE("VERTEX_DECLARATION_BIND", dev->SetVertexDeclaration(kind == 3 ? flatDecl : basicDecl));

    if (kind == 3) {
        const float wvp[16] = {
            0.945f, 0, 0, 0,
            0, 0.765f, 0, 0,
            0, 0, 0.55f, 0,
            0.023f, 0.00f, 0.1825f, 1
        };
        const float view[16] = {
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            0, 0, 0.15f, 1
        };
        const float fog[4] = {2.0f, 0.5f, 0.0f, 0.0f};
        const float fogColor[4] = {0.10f, 0.15f, 0.22f, 1.0f};
        CHECK_STATE("FLAT_WVP_CONSTANTS", dev->SetVertexShaderConstantF(0, wvp, 4));
        CHECK_STATE("FLAT_VIEW_CONSTANTS", dev->SetVertexShaderConstantF(4, view, 4));
        CHECK_STATE("FLAT_FOG_CONSTANT", dev->SetVertexShaderConstantF(8, fog, 1));
        CHECK_STATE("FLAT_PIXEL_FOG_CONSTANT", dev->SetPixelShaderConstantF(0, fogColor, 1));
        CHECK_STATE("FLAT_TEXTURE0_UNBIND", dev->SetTexture(0, NULL));
        CHECK_STATE("FLAT_TEXTURE1_UNBIND", dev->SetTexture(1, NULL));
    } else {
        bool constantsOk = true;
        SetBasicVertexConstants(dev, name, report, constantsOk);
        if (!constantsOk) {
            const HRESULT endFailureHr = dev->EndScene();
            if (FAILED(endFailureHr)) Log(report, std::string(name) + " ENDSCENE_AFTER_CONSTANT_FAIL " + Hr(endFailureHr));
            return false;
        }
        const float fogColor[4] = {0.10f, 0.15f, 0.22f, 1.0f};
        if (kind == 0) {
            CHECK_STATE("PIXEL_FOG_CONSTANT", dev->SetPixelShaderConstantF(0, fogColor, 1));
        } else if (kind == 1) {
            const float tint[4] = {1, 1, 1, 1};
            CHECK_STATE("UNLIT_TINT_CONSTANT", dev->SetPixelShaderConstantF(0, tint, 1));
            CHECK_STATE("UNLIT_FOG_CONSTANT", dev->SetPixelShaderConstantF(1, fogColor, 1));
        } else if (kind == 2) {
            const float waterTint[4] = {0.35f, 0.65f, 0.85f, 0.72f};
            const float uv0[4] = {0.13f, 0.07f, 0, 0};
            const float uv1[4] = {-0.09f, 0.11f, 0, 0};
            CHECK_STATE("WATER_TINT_CONSTANT", dev->SetPixelShaderConstantF(0, waterTint, 1));
            CHECK_STATE("WATER_UV0_CONSTANT", dev->SetPixelShaderConstantF(1, uv0, 1));
            CHECK_STATE("WATER_UV1_CONSTANT", dev->SetPixelShaderConstantF(2, uv1, 1));
            CHECK_STATE("WATER_FOG_CONSTANT", dev->SetPixelShaderConstantF(3, fogColor, 1));
        }
        CHECK_STATE("TEXTURE0_BIND", dev->SetTexture(0, tex0));
        CHECK_STATE("TEXTURE1_BIND", dev->SetTexture(1, kind == 2 ? tex1 : NULL));
        for (DWORD sampler = 0; sampler < 2; ++sampler) {
            CHECK_STATE("SAMPLER_MINFILTER", dev->SetSamplerState(sampler, D3DSAMP_MINFILTER, D3DTEXF_POINT));
            CHECK_STATE("SAMPLER_MAGFILTER", dev->SetSamplerState(sampler, D3DSAMP_MAGFILTER, D3DTEXF_POINT));
            CHECK_STATE("SAMPLER_MIPFILTER", dev->SetSamplerState(sampler, D3DSAMP_MIPFILTER, D3DTEXF_NONE));
            CHECK_STATE("SAMPLER_ADDRESSU", dev->SetSamplerState(sampler, D3DSAMP_ADDRESSU, D3DTADDRESS_WRAP));
            CHECK_STATE("SAMPLER_ADDRESSV", dev->SetSamplerState(sampler, D3DSAMP_ADDRESSV, D3DTADDRESS_WRAP));
        }
    }
#undef CHECK_STATE

    hr = dev->DrawPrimitiveUP(D3DPT_TRIANGLESTRIP, 2, kQuad, sizeof(Vertex));
    const HRESULT endHr = dev->EndScene();
    if (FAILED(hr)) { Log(report, std::string(name) + " DRAW_FAIL " + Hr(hr)); return false; }
    if (FAILED(endHr)) { Log(report, std::string(name) + " ENDSCENE_FAIL " + Hr(endHr)); return false; }

    std::string pixelDetail;
    readbackAvailable = ReadCenterPixel(dev, pixelDetail, pixelChanged, report);
    hr = dev->Present(NULL, NULL, NULL, NULL);
    if (FAILED(hr)) { Log(report, std::string(name) + " PRESENT_FAIL " + Hr(hr)); return false; }
    Log(report, std::string(name) + " DRAW_PRESENT_OK READBACK_AVAILABLE=" +
        (readbackAvailable ? "YES" : "NO") + " " + pixelDetail);
    return true;
}

static bool CreateLogged(HRESULT hr, const char* label, std::ofstream& report)
{
    Log(report, std::string(label) + (SUCCEEDED(hr) ? " CREATE_OK" : " CREATE_FAIL " + Hr(hr)));
    return SUCCEEDED(hr);
}

static bool RunDeviceMode(IDirect3D9* d3d, HWND window, D3DPRESENT_PARAMETERS* pp,
                          DWORD behavior, const char* modeName,
                          const std::vector<DWORD>& basicVSCode,
                          const std::vector<DWORD>& flatVSCode,
                          const std::vector<DWORD>& basicPSCode,
                          const std::vector<DWORD>& unlitPSCode,
                          const std::vector<DWORD>& waterPSCode,
                          const std::vector<DWORD>& flatPSCode,
                          std::ofstream& report)
{
    Log(report, std::string("=== DEVICE_MODE=") + modeName + " ===");
    IDirect3DDevice9* dev = NULL;
    HRESULT hr = d3d->CreateDevice(D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, window,
                                   behavior, pp, &dev);
    if (FAILED(hr)) {
        Log(report, std::string(modeName) + " DEVICE_CREATE_FAIL " + Hr(hr));
        return false;
    }
    Log(report, std::string(modeName) + " DEVICE_CREATE_OK");

    IDirect3DVertexShader9 *basicVS = NULL, *flatVS = NULL;
    IDirect3DPixelShader9 *basicPS = NULL, *unlitPS = NULL, *waterPS = NULL, *flatPS = NULL;
    IDirect3DVertexDeclaration9 *basicDecl = NULL, *flatDecl = NULL;
    IDirect3DTexture9 *tex0 = NULL, *tex1 = NULL;
    bool setupOk = true;

    setupOk = CreateLogged(dev->CreateVertexShader(basicVSCode.data(), &basicVS), "basic_vs20", report) && setupOk;
    setupOk = CreateLogged(dev->CreateVertexShader(flatVSCode.data(), &flatVS), "flat_lod_vs20", report) && setupOk;
    setupOk = CreateLogged(dev->CreatePixelShader(basicPSCode.data(), &basicPS), "basic_ps20", report) && setupOk;
    setupOk = CreateLogged(dev->CreatePixelShader(unlitPSCode.data(), &unlitPS), "unlit_ps20", report) && setupOk;
    setupOk = CreateLogged(dev->CreatePixelShader(waterPSCode.data(), &waterPS), "water_ps20", report) && setupOk;
    setupOk = CreateLogged(dev->CreatePixelShader(flatPSCode.data(), &flatPS), "flat_lod_ps20", report) && setupOk;
    setupOk = CreateLogged(dev->CreateVertexDeclaration(kBasicDecl, &basicDecl), "basic_vertex_declaration", report) && setupOk;
    setupOk = CreateLogged(dev->CreateVertexDeclaration(kFlatDecl, &flatDecl), "flat_vertex_declaration", report) && setupOk;
    if (setupOk) {
        const bool firstTextureOk = MakePatternTexture(dev, false, &tex0, report);
        const bool secondTextureOk = MakePatternTexture(dev, true, &tex1, report);
        setupOk = firstTextureOk && secondTextureOk;
        Log(report, std::string(modeName) + (setupOk ? " PATTERNED_TEXTURES_CREATE_OK" : " PATTERNED_TEXTURES_CREATE_FAIL"));
    }

    int drawPresentPassed = 0;
    int readbackAvailable = 0;
    int pixelsChanged = 0;
    const int totalCases = 5;
    if (setupOk) {
        bool readback = false;
        bool changed = false;
        if (RenderCase(dev, basicDecl, flatDecl, basicVS, flatVS, basicPS, tex0, tex1,
                       "BASIC_TEXTURED", 0, false, report, readback, changed)) ++drawPresentPassed;
        if (readback) ++readbackAvailable;
        if (changed) ++pixelsChanged;

        if (RenderCase(dev, basicDecl, flatDecl, basicVS, flatVS, unlitPS, tex0, tex1,
                       "UNLIT_TEXTURED", 1, false, report, readback, changed)) ++drawPresentPassed;
        if (readback) ++readbackAvailable;
        if (changed) ++pixelsChanged;

        if (RenderCase(dev, basicDecl, flatDecl, basicVS, flatVS, waterPS, tex0, tex1,
                       "WATER_TWO_TEXTURE_OPAQUE", 2, false, report, readback, changed)) ++drawPresentPassed;
        if (readback) ++readbackAvailable;
        if (changed) ++pixelsChanged;

        if (RenderCase(dev, basicDecl, flatDecl, basicVS, flatVS, waterPS, tex0, tex1,
                       "WATER_TWO_TEXTURE_ALPHA_BLEND", 2, true, report, readback, changed)) ++drawPresentPassed;
        if (readback) ++readbackAvailable;
        if (changed) ++pixelsChanged;

        if (RenderCase(dev, basicDecl, flatDecl, basicVS, flatVS, flatPS, tex0, tex1,
                       "FLAT_LOD", 3, false, report, readback, changed)) ++drawPresentPassed;
        if (readback) ++readbackAvailable;
        if (changed) ++pixelsChanged;
    } else {
        Log(report, std::string(modeName) + " SETUP_INCOMPLETE; draw tests skipped");
    }

    Log(report, std::string(modeName) + "_DRAW_PRESENT_PASSED=" + std::to_string(drawPresentPassed) + "/" + std::to_string(totalCases));
    Log(report, std::string(modeName) + "_READBACK_AVAILABLE=" + std::to_string(readbackAvailable) + "/" + std::to_string(totalCases));
    Log(report, std::string(modeName) + "_PIXEL_CHANGED=" + std::to_string(pixelsChanged) + "/" + std::to_string(totalCases));
    Log(report, std::string(modeName) + "_RESULT=" + ((setupOk && drawPresentPassed == totalCases) ? "PASS" : "FAIL"));

    if (tex1) tex1->Release();
    if (tex0) tex0->Release();
    if (flatDecl) flatDecl->Release();
    if (basicDecl) basicDecl->Release();
    if (flatPS) flatPS->Release();
    if (waterPS) waterPS->Release();
    if (unlitPS) unlitPS->Release();
    if (basicPS) basicPS->Release();
    if (flatVS) flatVS->Release();
    if (basicVS) basicVS->Release();
    dev->Release();
    return setupOk && drawPresentPassed == totalCases;
}

int main()
{
    std::ofstream report("D3D9ProbeReport.txt", std::ios::out | std::ios::trunc);
    if (!report) { std::cerr << "Cannot create D3D9ProbeReport.txt" << std::endl; return 2; }
    Log(report, "IV Legacy Shader Engine 0.3 - Direct3D 9 probe");
    Log(report, "Report values apply only to the machine on which this probe is run.");
    Log(report, "The probe separates HAL software-VP and hardware-VP device attempts.");
    Log(report, "Readback is best-effort; changed centre pixel is a smoke check, not visual correctness.");

    WNDCLASSA wc = {};
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = WindowProc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "IVLR_D3D9_PROBE_WINDOW";
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    if (!RegisterClassA(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        Log(report, "WINDOW_CLASS_FAIL");
        return 3;
    }
    g_window = CreateWindowA(wc.lpszClassName, "IV Legacy Shader Engine - D3D9 Probe",
        WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 800, 600,
        NULL, NULL, wc.hInstance, NULL);
    if (!g_window) { Log(report, "WINDOW_CREATE_FAIL"); return 3; }
    ShowWindow(g_window, SW_SHOW);
    UpdateWindow(g_window);

    IDirect3D9* d3d = Direct3DCreate9(D3D_SDK_VERSION);
    if (!d3d) {
        Log(report, "DIRECT3DCREATE9_FAIL");
        DestroyWindow(g_window);
        return 4;
    }

    D3DADAPTER_IDENTIFIER9 adapter = {};
    HRESULT hr = d3d->GetAdapterIdentifier(D3DADAPTER_DEFAULT, 0, &adapter);
    if (SUCCEEDED(hr)) {
        char adapterLine[512];
        std::snprintf(adapterLine, sizeof(adapterLine),
            "ADAPTER VendorId=0x%04lX DeviceId=0x%04lX SubsystemId=0x%08lX Revision=0x%04lX Description=%.180s",
            static_cast<unsigned long>(adapter.VendorId),
            static_cast<unsigned long>(adapter.DeviceId),
            static_cast<unsigned long>(adapter.SubSysId),
            static_cast<unsigned long>(adapter.Revision), adapter.Description);
        Log(report, adapterLine);
        char driverLine[256];
        std::snprintf(driverLine, sizeof(driverLine),
            "DRIVER=%s VERSION=%08lX:%08lX",
            adapter.Driver,
            static_cast<unsigned long>(adapter.DriverVersion.HighPart),
            static_cast<unsigned long>(adapter.DriverVersion.LowPart));
        Log(report, driverLine);
    } else {
        Log(report, std::string("ADAPTER_IDENTIFIER_FAIL ") + Hr(hr));
    }

    D3DCAPS9 caps = {};
    hr = d3d->GetDeviceCaps(D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, &caps);
    if (FAILED(hr)) {
        Log(report, std::string("GETCAPS_FAIL ") + Hr(hr));
        d3d->Release();
        DestroyWindow(g_window);
        return 4;
    }

    char capline[256];
    std::snprintf(capline, sizeof(capline),
        "CAPS VS=%u.%u PS=%u.%u MaxVSConst=%lu MaxFixedFunctionTextures=%lu DevCaps=0x%08lX",
        D3DSHADER_VERSION_MAJOR(caps.VertexShaderVersion), D3DSHADER_VERSION_MINOR(caps.VertexShaderVersion),
        D3DSHADER_VERSION_MAJOR(caps.PixelShaderVersion), D3DSHADER_VERSION_MINOR(caps.PixelShaderVersion),
        static_cast<unsigned long>(caps.MaxVertexShaderConst),
        static_cast<unsigned long>(caps.MaxSimultaneousTextures),
        static_cast<unsigned long>(caps.DevCaps));
    Log(report, capline);

    char ps20line[256];
    std::snprintf(ps20line, sizeof(ps20line),
        "PS20_CAPS Caps=0x%08lX NumInstructionSlots=%lu NumTemps=%lu StaticFlowControlDepth=%lu DynamicFlowControlDepth=%lu",
        static_cast<unsigned long>(caps.PS20Caps.Caps),
        static_cast<unsigned long>(caps.PS20Caps.NumInstructionSlots),
        static_cast<unsigned long>(caps.PS20Caps.NumTemps),
        static_cast<unsigned long>(caps.PS20Caps.StaticFlowControlDepth),
        static_cast<unsigned long>(caps.PS20Caps.DynamicFlowControlDepth));
    Log(report, ps20line);
    Log(report, std::string("ADAPTER_CAP_CHECK VS2=") +
        (caps.VertexShaderVersion >= D3DVS_VERSION(2,0) ? "YES" : "NO") +
        " PS2=" + (caps.PixelShaderVersion >= D3DPS_VERSION(2,0) ? "YES" : "NO") +
        " HW_TL=" + ((caps.DevCaps & D3DDEVCAPS_HWTRANSFORMANDLIGHT) ? "YES" : "NO"));

    std::vector<DWORD> basicVSCode, flatVSCode, basicPSCode, unlitPSCode, waterPSCode, flatPSCode;
    bool loaded = true;
    loaded = LoadBytecode("build\\out\\basic_vs20.vso", D3DVS_VERSION(2,0), basicVSCode, report) && loaded;
    loaded = LoadBytecode("build\\out\\flat_lod_vs20.vso", D3DVS_VERSION(2,0), flatVSCode, report) && loaded;
    loaded = LoadBytecode("build\\out\\basic_ps20.pso", D3DPS_VERSION(2,0), basicPSCode, report) && loaded;
    loaded = LoadBytecode("build\\out\\unlit_ps20.pso", D3DPS_VERSION(2,0), unlitPSCode, report) && loaded;
    loaded = LoadBytecode("build\\out\\water_ps20.pso", D3DPS_VERSION(2,0), waterPSCode, report) && loaded;
    loaded = LoadBytecode("build\\out\\flat_lod_ps20.pso", D3DPS_VERSION(2,0), flatPSCode, report) && loaded;
    if (!loaded) {
        Log(report, "STOP: shader bytecode is missing or invalid. Run build\\compile_shaders.bat first.");
        d3d->Release();
        DestroyWindow(g_window);
        return 6;
    }

    D3DPRESENT_PARAMETERS pp = {};
    pp.Windowed = TRUE;
    pp.SwapEffect = D3DSWAPEFFECT_DISCARD;
    pp.BackBufferFormat = D3DFMT_UNKNOWN;
    pp.BackBufferWidth = 640;
    pp.BackBufferHeight = 480;
    pp.PresentationInterval = D3DPRESENT_INTERVAL_IMMEDIATE;

    const bool swvpOk = RunDeviceMode(d3d, g_window, &pp, D3DCREATE_SOFTWARE_VERTEXPROCESSING,
        "HAL_SWVP", basicVSCode, flatVSCode, basicPSCode, unlitPSCode, waterPSCode, flatPSCode, report);

    const bool hardwareVpAdvertised = (caps.DevCaps & D3DDEVCAPS_HWTRANSFORMANDLIGHT) != 0 &&
                                      caps.VertexShaderVersion >= D3DVS_VERSION(2,0);
    bool hwvpOk = false;
    if (hardwareVpAdvertised) {
        hwvpOk = RunDeviceMode(d3d, g_window, &pp, D3DCREATE_HARDWARE_VERTEXPROCESSING,
            "HAL_HWVP", basicVSCode, flatVSCode, basicPSCode, unlitPSCode, waterPSCode, flatPSCode, report);
        if (!hwvpOk) Log(report, "HAL_HWVP_RESULT=FAILED_OR_INCOMPLETE; no software fallback was used for this mode");
    } else {
        Log(report, "HAL_HWVP_NOT_ATTEMPTED: required hardware transform/lighting or VS2 capability was not advertised");
    }

    Log(report, std::string("PRIMARY_SWVP_RESULT=") + (swvpOk ? "PASS" : "FAIL"));
    Log(report, std::string("HARDWARE_VP_RESULT=") +
        (!hardwareVpAdvertised ? "NOT_ADVERTISED" : (hwvpOk ? "PASS" : "FAIL")));
    Log(report, "Probe complete. Close the preview window to exit.");

    while (!g_quit) {
        MSG msg;
        while (PeekMessage(&msg, NULL, 0, 0, PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessage(&msg);
        }
        Sleep(20);
    }

    d3d->Release();
    if (g_window) DestroyWindow(g_window);
    UnregisterClassA(wc.lpszClassName, wc.hInstance);
    const int exitCode = swvpOk ? 0 : 10;
    Log(report, "EXIT_CODE=" + std::to_string(exitCode));
    return exitCode;
}
