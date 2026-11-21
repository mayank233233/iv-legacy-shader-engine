// IVLR flat distant-geometry vertex shader — Shader Model 2.0.
// Generic test interface only; not a GTA IV shader replacement.
row_major float4x4 WorldViewProjection : register(c0);
row_major float4x4 View               : register(c4);
float4 FogParameters        : register(c8); // X=end depth, Y=1/(end-start)

struct VS_INPUT
{
    float3 Position : POSITION0;
    float4 Color    : COLOR0;
};

struct VS_OUTPUT
{
    float4 Position  : POSITION0;
    float4 Color     : COLOR0;
    float  FogFactor : TEXCOORD0;
};

VS_OUTPUT VSMain(VS_INPUT input)
{
    VS_OUTPUT output;
    float4 position = float4(input.Position, 1.0);
    float4 viewPosition = mul(position, View);
    output.Position = mul(position, WorldViewProjection);
    output.Color = input.Color;
    output.FogFactor = saturate((FogParameters.x - viewPosition.z) * FogParameters.y);
    return output;
}
