// IVLR flat distant-geometry pass — Shader Model 2.0.
// No texture fetches. Intended for deliberately simplified distant materials.

float4 FogColor : register(c0);

struct PS_INPUT
{
    float4 Color     : COLOR0;
    float  FogFactor : TEXCOORD0;
};

float4 PSMain(PS_INPUT input) : COLOR0
{
    float3 color = lerp(FogColor.rgb, input.Color.rgb, saturate(input.FogFactor));
    return float4(color, input.Color.a);
}
