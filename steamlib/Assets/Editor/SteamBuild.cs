using UnityEditor;
using UnityEditor.SceneManagement;

public static class SteamBuild
{
    public static void Build()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        EditorSceneManager.SaveScene(scene, "Assets/Empty.unity");
        PlayerSettings.SetScriptingBackend(BuildTargetGroup.Standalone, ScriptingImplementation.Mono2x);
        EditorUserBuildSettings.SetPlatformSettings("Standalone", "OSXUniversal", "Architecture", "ARM64");
        var r = BuildPipeline.BuildPlayer(new BuildPlayerOptions {
            scenes = new[] { "Assets/Empty.unity" },
            locationPathName = "../build/SteamLib.app",
            target = BuildTarget.StandaloneOSX,
            options = BuildOptions.None
        });
        UnityEngine.Debug.Log("STEAMBUILD RESULT: " + r.summary.result);
        EditorApplication.Exit(r.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded ? 0 : 1);
    }
}
