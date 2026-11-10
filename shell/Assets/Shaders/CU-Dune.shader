// metal stand-in for Shader Graphs/DuneShader. its the one the dunemode console
// command uses (Resources/Special/DuneMaterial). per the bytecode it has _Dune times
// vertex color plus a discard at alpha 0 and normal 2D sprite lighting
Shader "CU/Dune"
{
    Properties
    {
        _Dune("Dune", 2D) = "white" {}
    }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "RenderPipeline"="UniversalPipeline" }
        Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
        Cull Off
        ZWrite Off

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
        #include "Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/Core2D.hlsl"
        TEXTURE2D(_Dune);
        SAMPLER(sampler_Dune);
        CBUFFER_START(UnityPerMaterial)
        float4 _Dune_TexelSize;
        CBUFFER_END
        half4 _RendererColor;

        half4 DuneVertexColor(float4 c)
        {
        #ifdef UNITY_INSTANCING_ENABLED
            return c * _RendererColor * unity_SpriteColor;
        #else
            return c * _RendererColor;
        #endif
        }

        half4 DuneColor(float2 uv, half4 color)
        {
            half4 c = SAMPLE_TEXTURE2D_BIAS(_Dune, sampler_Dune, uv, _GlobalMipBias.x) * color;
            clip(c.a == 0 ? -1 : 1);
            return c;
        }
        ENDHLSL

        Pass
        {
            Name "Sprite Lit"
            Tags { "LightMode"="Universal2D" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #pragma multi_compile USE_SHAPE_LIGHT_TYPE_0 __
            #pragma multi_compile USE_SHAPE_LIGHT_TYPE_1 __
            #pragma multi_compile USE_SHAPE_LIGHT_TYPE_2 __
            #pragma multi_compile USE_SHAPE_LIGHT_TYPE_3 __

            struct Attributes { float3 positionOS : POSITION; float4 color : COLOR; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct Varyings { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; half4 color : COLOR; half2 lightingUV : TEXCOORD1; UNITY_VERTEX_OUTPUT_STEREO };

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
                o.positionCS = TransformObjectToHClip(v.positionOS);
                o.uv = v.uv;
                o.color = DuneVertexColor(v.color);
                o.lightingUV = half2(ComputeScreenPos(o.positionCS / o.positionCS.w).xy);
                return o;
            }

            #include "Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/CombinedShapeLightShared.hlsl"

            half4 frag(Varyings i) : SV_Target
            {
                half4 c = DuneColor(i.uv, i.color);
                SurfaceData2D surfaceData;
                InputData2D inputData;
                InitializeSurfaceData(c.rgb, c.a, half4(1, 1, 1, 1), surfaceData);
                InitializeInputData(i.uv, i.lightingUV, inputData);
                return max(CombinedShapeLightShared(surfaceData, inputData), 0);
            }
            ENDHLSL
        }

        Pass
        {
            Name "Sprite Normal"
            Tags { "LightMode"="NormalsRendering" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing

            struct Attributes { float3 positionOS : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct Varyings { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; half3 normalWS : TEXCOORD1; UNITY_VERTEX_OUTPUT_STEREO };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionCS = TransformObjectToHClip(v.positionOS);
                o.uv = v.uv;
                o.normalWS = -GetViewForwardDir();
                return o;
            }

            // original writes the flat view normal packed to 0..1 with the texture's alpha
            half4 frag(Varyings i) : SV_Target
            {
                half a = SAMPLE_TEXTURE2D_BIAS(_Dune, sampler_Dune, i.uv, _GlobalMipBias.x).a;
                return half4(i.normalWS * 0.5 + 0.5, a);
            }
            ENDHLSL
        }

        Pass
        {
            Name "Sprite Forward"
            Tags { "LightMode"="UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing

            struct Attributes { float3 positionOS : POSITION; float4 color : COLOR; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct Varyings { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; half4 color : COLOR; UNITY_VERTEX_OUTPUT_STEREO };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionCS = TransformObjectToHClip(v.positionOS);
                o.uv = v.uv;
                o.color = DuneVertexColor(v.color);
                return o;
            }

            // original forward pass doesnt discard so this doesnt either
            half4 frag(Varyings i) : SV_Target
            {
                return SAMPLE_TEXTURE2D_BIAS(_Dune, sampler_Dune, i.uv, _GlobalMipBias.x) * i.color;
            }
            ENDHLSL
        }
    }
}
