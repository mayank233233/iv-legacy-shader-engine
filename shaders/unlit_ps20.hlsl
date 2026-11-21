// IVLR unlit textured material — Shader Model 2.0.
// Suitable only for materials whose lighting is handled elsewhere.

sampler2D DiffuseSampler : register(s0);
float4 TintColor : register(c0);
float4 FogColor : register(c1);

struct PS_INPUT
{
    float2 TexCoord  : TEXCOORD0;
    float  FogFactor : TEXCOORD1;
};

float4 PSMain(PS_INPUT input) : COLOR0
{
    float4 texel = tex2D(DiffuseSampler, input.TexCoord);
    float3 surface = texel.rgb * TintColor.rgb;
    float3 finalColor = lerp(FogColor.rgb, surface, saturate(input.FogFactor));

    return float4(finalColor, texel.a * TintColor.a);
}
