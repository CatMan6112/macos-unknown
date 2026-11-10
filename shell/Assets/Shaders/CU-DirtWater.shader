// metal stand-in for Shader Graphs/DirtWaterShader. the real code is in CULiquid.hlsl
Shader "CU/DirtWater"
{
    Properties
    {
        _ReflecHeight("ReflecHeight", Float) = 0.5
        _SampleTexture2D_b09e3456ac1444539b53e06208e61251_Texture_1_Texture2D("Texture2D", 2D) = "white" {}
        _SampleTexture2D_e7896186ac794a1fa26e453638d2716d_Texture_1_Texture2D("Texture2D", 2D) = "white" {}
    }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "RenderPipeline"="UniversalPipeline" }
        Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
        Cull Off
        ZWrite Off
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
            #define LIQUID_DIRT
            #define CU_PASS_LIT
            #include "CULiquid.hlsl"
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
            #define LIQUID_DIRT
            #define CU_PASS_NORMAL
            #include "CULiquid.hlsl"
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
            #define LIQUID_DIRT
            #define CU_PASS_FORWARD
            #include "CULiquid.hlsl"
            ENDHLSL
        }
    }
}
