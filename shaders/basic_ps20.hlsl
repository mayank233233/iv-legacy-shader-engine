// IVLR basic textured material — Shader Model 2.0.
// One texture lookup; lighting is calculated per vertex in basic_vs20.hlsl.

sampler2D DiffuseSampler : register(s0);
float4 FogColor : register(c0); // RGB fog colour, A unused

struct PS_INPUT
{
    float2 TexCoord  : TEXCOORD0;
    float4 LitColor  : COLOR0;
    float  FogFactor : TEXCOORD1;
};

float4 PSMain(PS_INPUT input) : COLOR0
{
    float4 texel = tex2D(DiffuseSampler, input.TexCoord);
    float3 surface = texel.rgb * input.LitColor.rgb;
    float3 finalColor = lerp(FogColor.rgb, surface, saturate(input.FogFactor));

    return float4(finalColor, texel.a);
}
