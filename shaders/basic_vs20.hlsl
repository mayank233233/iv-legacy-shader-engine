// IVLR basic vertex shader — Shader Model 2.0.
// Generic test interface only; not a GTA IV shader replacement.
// Matrices use row-vector mul convention. Keep the test matrices identity.

row_major float4x4 WorldViewProjection       : register(c0);
row_major float4x4 World                     : register(c4);
row_major float4x4 WorldInverseTranspose    : register(c8);
row_major float4x4 View                      : register(c12);
float4 AmbientColor                : register(c16);
float4 DiffuseColor                : register(c17);
float4 LightDirection               : register(c18);
float4 FogParameters                : register(c19); // X=end depth, Y=1/(end-start)

struct VS_INPUT
{
    float3 Position : POSITION0;
    float3 Normal   : NORMAL0;
    float2 TexCoord : TEXCOORD0;
};

struct VS_OUTPUT
{
    float4 Position  : POSITION0;
    float2 TexCoord  : TEXCOORD0;
    float4 LitColor  : COLOR0;
    float  FogFactor : TEXCOORD1;
};

VS_OUTPUT VSMain(VS_INPUT input)
{
    VS_OUTPUT output;
    float4 objectPosition = float4(input.Position, 1.0);
    float4 worldPosition = mul(objectPosition, World);
    float4 viewPosition = mul(worldPosition, View);
    float3 worldNormal = normalize(mul(input.Normal, (float3x3)WorldInverseTranspose));
    float3 lightDir = normalize(LightDirection.xyz);
    float diffuseTerm = saturate(dot(worldNormal, lightDir));
    float3 lighting = AmbientColor.rgb + DiffuseColor.rgb * diffuseTerm;

    output.Position = mul(objectPosition, WorldViewProjection);
    output.TexCoord = input.TexCoord;
    output.LitColor = float4(saturate(lighting), 1.0);
    output.FogFactor = saturate((FogParameters.x - viewPosition.z) * FogParameters.y);
    return output;
}
