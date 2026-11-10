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
        EditorUserBuildSettings.SetPlatformSettings("Standalone", "OSXUniversal", "Architecture", "ARM64");

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
