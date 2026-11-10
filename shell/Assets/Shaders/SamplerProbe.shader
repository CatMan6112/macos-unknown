// game never uses this. its only here so the compiled m_Samplers flags show how
// unity encodes inline sampler names, thats where dx2hlsl.py's table came from
Shader "CU/SamplerProbe"
{
    SubShader
    {
        Pass
        {
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            Texture2D _T0; Texture2D _T1; Texture2D _T2; Texture2D _T3; Texture2D _T4; Texture2D _T5; Texture2D _T6;
            SamplerState sampler_p_Point_Repeat;
            SamplerState sampler_p_Point_Clamp;
            SamplerState sampler_p_Linear_Repeat;
            SamplerState sampler_p_Linear_Clamp;
            SamplerState sampler_p_Linear_Mirror;
            SamplerState sampler_p_Point_Mirror;
            SamplerState sampler_p_Trilinear_Clamp;
            float4 vert(float4 p : POSITION) : SV_POSITION { return p; }
            float4 frag(float4 p : SV_POSITION) : SV_Target
            {
                float2 uv = p.xy;
                return _T0.Sample(sampler_p_Point_Repeat, uv) + _T1.Sample(sampler_p_Point_Clamp, uv)
                     + _T2.Sample(sampler_p_Linear_Repeat, uv) + _T3.Sample(sampler_p_Linear_Clamp, uv)
                     + _T4.Sample(sampler_p_Linear_Mirror, uv) + _T5.Sample(sampler_p_Point_Mirror, uv)
                     + _T6.Sample(sampler_p_Trilinear_Clamp, uv);
            }
            ENDHLSL
        }
    }
}
