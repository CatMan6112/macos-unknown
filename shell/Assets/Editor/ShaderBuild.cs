using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

// builds build/ShaderShell.app. its the shell with every non shader graph shader the
// game uses stuffed in Always Included so it compiles for metal. swap-shaders.py
// copies them out after
public static class ShaderBuild
{
    public static void Build()
    {
        // game is linear. shaders compile different per color space and a gamma
        // donor makes bloom and lighting bright as shit
        PlayerSettings.colorSpace = ColorSpace.Linear;

        var names = File.ReadAllLines("shader-wanted.txt");
        var shaders = new List<Shader>();
        foreach (var n in names)
        {
            if (n.Trim().Length == 0) continue;
            var s = Shader.Find(n);
            if (s == null) { Debug.Log("SHADERBUILD MISSING: " + n); continue; }
            shaders.Add(s);
        }

        var gs = new SerializedObject(GraphicsSettings.GetGraphicsSettings());
        var list = gs.FindProperty("m_AlwaysIncludedShaders");
        list.ClearArray();
        for (int i = 0; i < shaders.Count; i++)
        {
            list.InsertArrayElementAtIndex(i);
            list.GetArrayElementAtIndex(i).objectReferenceValue = shaders[i];
        }
        gs.ApplyModifiedProperties();

        // keep every variant cause the game uses keywords the shell never touches
        var glob = AssetDatabase.LoadMainAssetAtPath("Assets/UniversalRenderPipelineGlobalSettings.asset");
        var so = new SerializedObject(glob);
        foreach (var p in new[] { "m_StripDebugVariants", "m_StripUnusedPostProcessingVariants",
                                  "m_StripUnusedVariants", "m_StripUnusedLODCrossFadeVariants",
                                  "m_StripScreenCoordOverrideVariants" })
        {
            var prop = so.FindProperty(p);
            if (prop != null) prop.boolValue = false;
        }
        so.ApplyModifiedProperties();
        AssetDatabase.SaveAssets();
        Debug.Log("SHADERBUILD INCLUDED: " + shaders.Count + " of " + names.Length);

        var r = BuildPipeline.BuildPlayer(new BuildPlayerOptions {
            scenes = new[] { "Assets/Scenes/Empty.unity" },
            locationPathName = "../build/ShaderShell.app",
            target = BuildTarget.StandaloneOSX,
            options = BuildOptions.None
        });
        Debug.Log("SHADERBUILD RESULT: " + r.summary.result + " size=" + r.summary.totalSize);
        EditorApplication.Exit(r.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded ? 0 : 1);
    }
}
