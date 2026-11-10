using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

public static class ShellBuild
{
    public static void Build()
    {
        var rd = ScriptableObject.CreateInstance<Renderer2DData>();
        AssetDatabase.CreateAsset(rd, "Assets/Renderer2D.asset");
        var urp = UniversalRenderPipelineAsset.Create(rd);
        AssetDatabase.CreateAsset(urp, "Assets/URP2D.asset");
        AssetDatabase.SaveAssets();
        GraphicsSettings.renderPipelineAsset = urp;
        QualitySettings.renderPipeline = urp;

        var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
        EditorSceneManager.SaveScene(scene, "Assets/Scenes/Empty.unity");

        PlayerSettings.companyName = "Orsoniks";
        PlayerSettings.productName = "CasualtiesUnknown";
        PlayerSettings.SetScriptingBackend(BuildTargetGroup.Standalone, ScriptingImplementation.Mono2x);
        PlayerSettings.SetGraphicsAPIs(BuildTarget.StandaloneOSX, new[] { GraphicsDeviceType.Metal });
        // universal so intel macs work too. costs about 100 MB in the payload
        EditorUserBuildSettings.SetPlatformSettings("Standalone", "OSXUniversal", "Architecture", "x64ARM64");

        // ShaderBuild leaves its settings in this project and the game goes solid magenta
        // so put the shell ones back
        PlayerSettings.colorSpace = ColorSpace.Gamma;
        var gs = new SerializedObject(GraphicsSettings.GetGraphicsSettings());
        var list = gs.FindProperty("m_AlwaysIncludedShaders");
        list.ClearArray();
        int n = 0;
        foreach (var name in System.IO.File.ReadAllLines("shell-included.txt"))
        {
            if (name.Trim().Length == 0) continue;
            var s = Shader.Find(name);
            if (s == null) { Debug.Log("SHELLBUILD MISSING: " + name); continue; }
            list.InsertArrayElementAtIndex(n);
            list.GetArrayElementAtIndex(n++).objectReferenceValue = s;
        }
        gs.ApplyModifiedProperties();
        var glob = AssetDatabase.LoadMainAssetAtPath("Assets/UniversalRenderPipelineGlobalSettings.asset");
        if (glob != null)
        {
            var so = new SerializedObject(glob);
            foreach (var p in new[] { "m_StripDebugVariants", "m_StripUnusedPostProcessingVariants",
                                      "m_StripUnusedVariants", "m_StripUnusedLODCrossFadeVariants",
                                      "m_StripScreenCoordOverrideVariants" })
            {
                var prop = so.FindProperty(p);
                if (prop != null) prop.boolValue = true;
            }
            so.ApplyModifiedProperties();
        }
        AssetDatabase.SaveAssets();
        Debug.Log("SHELLBUILD INCLUDED: " + n);

        var r = BuildPipeline.BuildPlayer(new BuildPlayerOptions {
            scenes = new[] { "Assets/Scenes/Empty.unity" },
            locationPathName = "../build/Shell.app",
            target = BuildTarget.StandaloneOSX,
            options = BuildOptions.None
        });
        Debug.Log("SHELLBUILD RESULT: " + r.summary.result + " size=" + r.summary.totalSize);
        EditorApplication.Exit(r.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded ? 0 : 1);
    }
}
