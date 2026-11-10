// hand port of the liquid shader graphs (Water DirtWater Oil Sap and Algae) off
// their D3D11 bytecode. each .shader defines LIQUID_<KIND> and CU_PASS_<PASS>
// then includes this
//
// all of them do the same thing. two scrolling Simple Noise fields (scale 8)
// wobble a screen space lookup of WATERPLEASE and LIQUIDCIRCLE is the alpha shape

#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
#include "Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/Core2D.hlsl"
#include "Packages/com.unity.render-pipelines.core/ShaderLibrary/Hashes.hlsl"

#if defined(LIQUID_WATER)
    #define LIQ_SCROLL float4(0.025, 0.025, -0.024, -0.024)
    #define LIQ_DRIFT 0.1
#elif defined(LIQUID_DIRT)
    #define LIQ_SCROLL float4(0.025, 0.025, -0.024, -0.024)
    #define LIQ_DRIFT 0.1
#elif defined(LIQUID_OIL)
    #define LIQ_SCROLL float4(0.015, 0.015, -0.014, -0.014)
    #define LIQ_DRIFT 0.04
#elif defined(LIQUID_SAP)
    #define LIQ_SCROLL float4(0.005, 0.005, -0.004, -0.004)
    #define LIQ_DRIFT 0.01
#elif defined(LIQUID_ALGAE)
    #define LIQ_SCROLL float4(0.025, 0.025, -0.024, -0.024)
    #define LIQ_DRIFT 0.1
#endif

TEXTURE2D(_SampleTexture2D_b09e3456ac1444539b53e06208e61251_Texture_1_Texture2D);
SAMPLER(sampler_SampleTexture2D_b09e3456ac1444539b53e06208e61251_Texture_1_Texture2D);
TEXTURE2D(_SampleTexture2D_e7896186ac794a1fa26e453638d2716d_Texture_1_Texture2D);
SAMPLER(sampler_SampleTexture2D_e7896186ac794a1fa26e453638d2716d_Texture_1_Texture2D);
#define LIQ_TEX _SampleTexture2D_b09e3456ac1444539b53e06208e61251_Texture_1_Texture2D
#define LIQ_MASK _SampleTexture2D_e7896186ac794a1fa26e453638d2716d_Texture_1_Texture2D

#if defined(LIQUID_WATER)
TEXTURE2D(_CameraSortingLayerTexture);
SAMPLER(sampler_CameraSortingLayerTexture);
#endif

CBUFFER_START(UnityPerMaterial)
float _ReflecHeight;
float4 _SampleTexture2D_b09e3456ac1444539b53e06208e61251_Texture_1_Texture2D_TexelSize;
float4 _SampleTexture2D_e7896186ac794a1fa26e453638d2716d_Texture_1_Texture2D_TexelSize;
CBUFFER_END

half4 _RendererColor;

half4 CULiq_VertexColor(float4 c)
{
#ifdef UNITY_INSTANCING_ENABLED
    return c * _RendererColor * unity_SpriteColor;
#else
    return c * _RendererColor;
#endif
}

float CULiq_ValueNoise(float2 uv)
{
    float2 i = floor(uv);
    float2 f = frac(uv);
    f = f * f * (3.0 - 2.0 * f);
    float r0, r1, r2, r3;
    Hash_Tchou_2_1_float(i + float2(0, 0), r0);
    Hash_Tchou_2_1_float(i + float2(1, 0), r1);
    Hash_Tchou_2_1_float(i + float2(0, 1), r2);
    Hash_Tchou_2_1_float(i + float2(1, 1), r3);
    return lerp(lerp(r0, r1, f.x), lerp(r2, r3, f.x), f.y);
}

// shader graph Simple Noise (deterministic) at scale 8
float CULiq_SimpleNoise(float2 uv)
{
    return CULiq_ValueNoise(uv * 8.0) * 0.125
         + CULiq_ValueNoise(uv * 4.0) * 0.25
         + CULiq_ValueNoise(uv * 2.0) * 0.5;
}

// shader graph Voronoi (deterministic hash) that gives distance to the nearest cell point
float CULiq_Voronoi(float2 uv, float angleOffset)
{
    float2 g = floor(uv);
    float2 f = frac(uv);
    float best = 8.0;
    [unroll] for (int y = -1; y <= 1; y++)
    [unroll] for (int x = -1; x <= 1; x++)
    {
        float2 lattice = float2(x, y);
        float2 h;
        Hash_Tchou_2_2_float(lattice + g, h);
        float2 o = float2(sin(h.y * angleOffset), cos(h.x * angleOffset)) * 0.5 + 0.5;
        best = min(best, distance(lattice + o, f));
    }
    return best;
}

// matches the graph's Screen Position node on both D3D and metal
float2 CULiq_ScreenUV(float4 positionCS)
{
    float2 s = positionCS.xy / _ScaledScreenParams.xy;
    if (_ProjectionParams.x < 0) s.y = 1.0 - s.y;
    s.y = 1.0 - s.y;
    return s;
}

half4 CULiq_Color(float4 positionCS, float2 uv, half4 vertexColor, float3 positionWS)
{
    float t = _TimeParameters.x;
    float4 nuv = t * LIQ_SCROLL + uv.xyxy;
    float n = CULiq_SimpleNoise(nuv.xy) * CULiq_SimpleNoise(nuv.zw) - 0.5;
    float2 offs = n * 0.5 + float2(t * LIQ_DRIFT, 0);
    float2 suv = CULiq_ScreenUV(positionCS);
    half4 tex = SAMPLE_TEXTURE2D_BIAS(LIQ_TEX, sampler_SampleTexture2D_b09e3456ac1444539b53e06208e61251_Texture_1_Texture2D, suv + offs, _GlobalMipBias.x);
    half mask = SAMPLE_TEXTURE2D_BIAS(LIQ_MASK, sampler_SampleTexture2D_e7896186ac794a1fa26e453638d2716d_Texture_1_Texture2D, uv, _GlobalMipBias.x).a;
    half4 c;
#if defined(LIQUID_WATER)
    half3 grab = SAMPLE_TEXTURE2D_BIAS(_CameraSortingLayerTexture, sampler_CameraSortingLayerTexture,
                                       suv + float2(0, 0.1) + tex.rg * 0.15, _GlobalMipBias.x).rgb;
    c.rgb = lerp(tex.rgb, grab, 0.5);
    c.a = lerp(tex.b, 1.0, 0.65) * mask;
#elif defined(LIQUID_DIRT)
    c.rgb = lerp(0.217638, tex.rgb, 0.4) * half3(0.591114, 0.488356, 0.425611);
    c.a = lerp(tex.b, 1.0, 0.65) * mask;
#elif defined(LIQUID_OIL)
    c.rgb = tex.rgb * 2.0;
    c.a = lerp(tex.b, 1.0, 0.95) * lerp(mask, 1.0, 0.5);
#elif defined(LIQUID_SAP)
    c.rgb = tex.rgb * half3(1.0, 0.459832, 0.108526);
    c.a = lerp(tex.b, 1.0, 0.9) * mask;
#elif defined(LIQUID_ALGAE)
    // voronoi on world xy. cells drift over time and glow near the points
    half glow = (1.0 - CULiq_Voronoi(positionWS.xy, t * 0.3)) >= 0.93 ? 1.0 : 0.0;
    c.rgb = tex.rgb * half3(0.54, 1.51, 0.63) + glow * half3(0.656394, 5.99216, 0.254384);
    c.a = max(lerp(tex.b, 1.0, 0.8), glow) * mask;
#endif
    c *= vertexColor;
    clip(c.a == 0 ? -1 : 1);
    return c;
}

#if defined(CU_PASS_LIT)

struct Attributes { float3 positionOS : POSITION; float4 color : COLOR; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
struct Varyings { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; half4 color : COLOR; half2 lightingUV : TEXCOORD1; float3 positionWS : TEXCOORD4; UNITY_VERTEX_OUTPUT_STEREO };

#include "Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/LightingUtility.hlsl"
#if USE_SHAPE_LIGHT_TYPE_0
SHAPE_LIGHT(0)
#endif
#if USE_SHAPE_LIGHT_TYPE_1
SHAPE_LIGHT(1)
#endif
#if USE_SHAPE_LIGHT_TYPE_2
SHAPE_LIGHT(2)
#endif
#if USE_SHAPE_LIGHT_TYPE_3
SHAPE_LIGHT(3)
#endif

Varyings vert(Attributes v)
{
    Varyings o = (Varyings)0;
    UNITY_SETUP_INSTANCE_ID(v);
    UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
    o.positionWS = TransformObjectToWorld(v.positionOS);
    o.positionCS = TransformWorldToHClip(o.positionWS);
    o.uv = v.uv;
    o.color = CULiq_VertexColor(v.color);
    o.lightingUV = half2(ComputeScreenPos(o.positionCS / o.positionCS.w).xy);
    return o;
}

#include "Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/CombinedShapeLightShared.hlsl"

half4 frag(Varyings i) : SV_Target
{
    half4 c = CULiq_Color(i.positionCS, i.uv, i.color, i.positionWS);
    SurfaceData2D surfaceData;
    InputData2D inputData;
    InitializeSurfaceData(c.rgb, c.a, half4(1, 1, 1, 1), surfaceData);
    InitializeInputData(i.uv, i.lightingUV, inputData);
    return max(CombinedShapeLightShared(surfaceData, inputData), 0);
}

#elif defined(CU_PASS_NORMAL)

struct Attributes { float3 positionOS : POSITION; float4 color : COLOR; float2 uv : TEXCOORD0; float4 tangent : TANGENT; UNITY_VERTEX_INPUT_INSTANCE_ID };
struct Varyings { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; half4 color : COLOR; half3 normalWS : TEXCOORD1; half3 tangentWS : TEXCOORD2; half3 bitangentWS : TEXCOORD3; float3 positionWS : TEXCOORD4; UNITY_VERTEX_OUTPUT_STEREO };

Varyings vert(Attributes v)
{
    Varyings o = (Varyings)0;
    UNITY_SETUP_INSTANCE_ID(v);
    UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
    o.positionWS = TransformObjectToWorld(v.positionOS);
    o.positionCS = TransformWorldToHClip(o.positionWS);
    o.uv = v.uv;
    o.color = CULiq_VertexColor(v.color);
    o.normalWS = -GetViewForwardDir();
    o.tangentWS = TransformObjectToWorldDir(v.tangent.xyz);
    o.bitangentWS = cross(o.normalWS, o.tangentWS) * v.tangent.w;
    return o;
}

#include "Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/NormalsRenderingShared.hlsl"

half4 frag(Varyings i) : SV_Target
{
    half4 c = CULiq_Color(i.positionCS, i.uv, i.color, i.positionWS);
    return NormalsRenderingShared(c, half3(0, 0, 1), i.tangentWS, i.bitangentWS, i.normalWS);
}

#elif defined(CU_PASS_FORWARD)

struct Attributes { float3 positionOS : POSITION; float4 color : COLOR; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
struct Varyings { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; half4 color : COLOR; float3 positionWS : TEXCOORD4; UNITY_VERTEX_OUTPUT_STEREO };

Varyings vert(Attributes v)
{
    Varyings o = (Varyings)0;
    UNITY_SETUP_INSTANCE_ID(v);
    UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
    o.positionWS = TransformObjectToWorld(v.positionOS);
    o.positionCS = TransformWorldToHClip(o.positionWS);
    o.uv = v.uv;
    o.color = CULiq_VertexColor(v.color);
    return o;
}

half4 frag(Varyings i) : SV_Target
{
    return max(CULiq_Color(i.positionCS, i.uv, i.color, i.positionWS), 0);
}

#endif
