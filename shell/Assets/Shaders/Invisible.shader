// stopgap for shader graphs with no metal build that draws nothing. two passes cause
// the fullscreen graphs have two and URP picks one by index
Shader "CU/Invisible"
{
    SubShader
    {
        Tags { "RenderType"="Transparent" "Queue"="Transparent" }
        Pass
        {
            ZWrite Off ZTest Always Cull Off Blend Zero One ColorMask 0
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            float4 vert(uint id : SV_VertexID) : SV_POSITION { return float4(0, 0, 2, 1); }
            half4 frag() : SV_Target { return 0; }
            ENDHLSL
        }
        Pass
        {
            ZWrite Off ZTest Always Cull Off Blend Zero One ColorMask 0
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            float4 vert(uint id : SV_VertexID) : SV_POSITION { return float4(0, 0, 2, 1); }
            half4 frag() : SV_Target { return 0; }
            ENDHLSL
        }
    }
}
