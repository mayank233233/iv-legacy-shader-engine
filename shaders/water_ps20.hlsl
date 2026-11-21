// IVLR low-cost water approximation — Shader Model 2.0.
// Two scrolling texture samples; no screen-space reflection, refraction,
// dynamic branching, dependent multi-pass effects, or normal-map lighting.

sampler2D WaterLayer0 : register(s0);
sampler2D WaterLayer1 : register(s1);

float4 WaterTint : register(c0);       // RGB tint, A opacity multiplier
float4 WaterUVOffset0 : register(c1);  // XY offset
float4 WaterUVOffset1 : register(c2);  // XY offset
float4 FogColor : register(c3);

struct PS_INPUT
{
    float2 TexCoord  : TEXCOORD0;
    float  FogFactor : TEXCOORD1;
};

float4 PSMain(PS_INPUT input) : COLOR0
{
    float2 uv0 = input.TexCoord + WaterUVOffset0.xy;
    float2 uv1 = input.TexCoord * 1.37 + WaterUVOffset1.xy;

    float4 layer0 = tex2D(WaterLayer0, uv0);
    float4 layer1 = tex2D(WaterLayer1, uv1);

    float3 water = (layer0.rgb * 0.65 + layer1.rgb * 0.35) * WaterTint.rgb;
    float3 finalColor = lerp(FogColor.rgb, water, saturate(input.FogFactor));
    float alpha = saturate((layer0.a * 0.65 + layer1.a * 0.35) * WaterTint.a);

    return float4(finalColor, alpha);
}
