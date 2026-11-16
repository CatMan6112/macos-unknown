// mod bundles built on windows only have d3d11 shaders so they draw pink on metal.
// anything new after a bundle load counts as a mod shader cause isSupported lies about QoL's fonts
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.RegularExpressions;
using BepInEx;
using BepInEx.Logging;
using HarmonyLib;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace MacosUnknown
{
    // BepInEx goes in GUID order so the 0 loads this before mods that load bundles in Awake
    [BepInPlugin("0.macosunknown.shaderswap", "Shader Swap", "1.0.0")]
    public class ShaderSwap : BaseUnityPlugin
    {
        static ManualLogSource log;
        static bool on;
        static bool dirty;
        static int lastSweep = -1;
        static readonly HashSet<int> modShaders = new HashSet<int>();
        static readonly Dictionary<string, Shader> twins = new Dictionary<string, Shader>();
        static readonly HashSet<string> told = new HashSet<string>();

        void Awake()
        {
            log = Logger;
            on = MacMods();
            if (!on)
            {
                log.LogInfo("MacOS enhancements are off, leaving mod shaders alone");
                return;
            }
            var h = new Harmony("0.macosunknown.shaderswap");
            var pre = new HarmonyMethod(typeof(ShaderSwap).GetMethod(nameof(Before), BindingFlags.Static | BindingFlags.NonPublic));
            var post = new HarmonyMethod(typeof(ShaderSwap).GetMethod(nameof(Loaded), BindingFlags.Static | BindingFlags.NonPublic));
            var ab = typeof(AssetBundle);
            // harmony cant patch AssetBundleRequest.allAssets cause its native. the scene load sweep gets those
            Patch(h, pre, post, Method(ab, "LoadAsset", typeof(string)));
            Patch(h, pre, post, Method(ab, "LoadAsset", typeof(string), typeof(Type)));
            Patch(h, pre, post, Method(ab, "LoadAssetWithSubAssets", typeof(string), typeof(Type)));
            Patch(h, pre, post, Method(ab, "LoadAllAssets", typeof(Type)));
            Patch(h, pre, post, Getter(typeof(AssetBundleRequest), "asset"));
            SceneManager.sceneLoaded += (s, m) => Sweep();
        }

        void Start()
        {
            if (on) Sweep();
        }

        void LateUpdate()
        {
            if (on && dirty) Sweep();
        }

        // the MacOS enhancements box, same check as CUPort.dll. CUPORT_MACMODS=0/1 beats launcher.json
        static bool MacMods()
        {
            string env = Environment.GetEnvironmentVariable("CUPORT_MACMODS");
            if (env == "0" || env == "1")
                return env == "1";
            try
            {
                string path = Path.Combine(Environment.GetEnvironmentVariable("HOME") ?? "",
                    "Library/Application Support/macos-unknown/launcher.json");
                return !Regex.IsMatch(File.ReadAllText(path), "\"macmods\"\\s*:\\s*false");
            }
            catch (Exception)
            {
                return true;
            }
        }

        // GetMethod with a type list also matches LoadAsset<T>(string) and throws
        static MethodInfo Method(Type t, string name, params Type[] args)
        {
            foreach (var m in t.GetMethods(BindingFlags.Public | BindingFlags.Instance))
            {
                if (m.Name != name || m.IsGenericMethodDefinition) continue;
                var ps = m.GetParameters();
                if (ps.Length != args.Length) continue;
                bool same = true;
                for (int i = 0; i < ps.Length; i++) same &= ps[i].ParameterType == args[i];
                if (same) return m;
            }
            return null;
        }

        // AssetBundleRequest.asset hides ResourceRequest.asset, so ask for its own one
        static MethodInfo Getter(Type t, string name)
        {
            var p = t.GetProperty(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly);
            return p == null ? null : p.GetGetMethod();
        }

        static void Patch(Harmony h, HarmonyMethod pre, HarmonyMethod post, MethodInfo m)
        {
            if (m == null)
            {
                log.LogWarning("an AssetBundle method is missing, bundles loaded that way get fixed on the next scene load");
                return;
            }
            try { h.Patch(m, prefix: pre, postfix: post); }
            catch (Exception e) { log.LogWarning($"couldnt patch {m.Name}: {e.Message}"); }
        }

        static HashSet<int> ShaderIds()
        {
            var ids = new HashSet<int>();
            foreach (var s in Resources.FindObjectsOfTypeAll<Shader>())
                if (s != null) ids.Add(s.GetInstanceID());
            return ids;
        }

        static void Before(out HashSet<int> __state)
        {
            try { __state = ShaderIds(); }
            catch (Exception) { __state = null; }
        }

        // shaders that exist now and didnt before came out of the bundle. one sweep a frame tops
        // and LateUpdate gets the rest, plus copies TMP made from a broken material in between
        static void Loaded(HashSet<int> __state)
        {
            try
            {
                if (__state != null)
                    foreach (var id in ShaderIds())
                        if (!__state.Contains(id)) modShaders.Add(id);
                // a later load can bring new materials on a mod shader we already know
                dirty = true;
                if (Time.frameCount != lastSweep) Sweep();
            }
            catch (Exception) { dirty = true; }
        }

        static void Sweep()
        {
            lastSweep = Time.frameCount;
            dirty = false;
            foreach (var m in Resources.FindObjectsOfTypeAll<Material>())
            {
                if (m == null) continue;
                var from = m.shader;
                // Hidden/ is unity's own stuff, InternalErrorShader included. never touch it
                if (from == null || from.name.StartsWith("Hidden/")) continue;
                bool mod = modShaders.Contains(from.GetInstanceID());
                if (!mod && from.isSupported) continue;
                var to = Twin(from.name);
                // a supported mod shader with no game twin is probably real metal code, leave it
                if (to == null && mod && from.isSupported) continue;
                if (to == null) to = Fallback(from.name);
                if (to == null || to == from) continue;
                int queue = m.renderQueue;
                m.shader = to;
                m.renderQueue = queue;
                if (told.Add(from.name + ">" + to.name))
                    log.LogInfo(from.name == to.name ? $"swapped {from.name}" : $"no metal {from.name}, using {to.name}");
            }
        }

        static Shader Twin(string name)
        {
            Shader s;
            if (twins.TryGetValue(name, out s) && s != null) return s;
            s = GameShader(name);
            if (s != null) twins[name] = s;
            return s;
        }

        // not cached, so a real twin that loads later still wins
        static Shader Fallback(string name)
        {
            var s = name.Contains("TextMeshPro")
                ? GameShader("TextMeshPro/Distance Field") ?? GameShader("TextMeshPro/Mobile/Distance Field")
                : GameShader("Universal Render Pipeline/2D/Sprite-Lit-Default") ?? GameShader("Sprites/Default");
            if (s == null && told.Add(name))
                log.LogWarning($"no metal shader for {name} yet, it stays broken");
            return s;
        }

        // same name as the mod's copy, so Shader.Find alone can hand back the broken one
        static Shader GameShader(string name)
        {
            foreach (var s in Resources.FindObjectsOfTypeAll<Shader>())
                if (s != null && s.name == name && s.isSupported && !modShaders.Contains(s.GetInstanceID())) return s;
            var f = Shader.Find(name);
            return f != null && f.isSupported && !modShaders.Contains(f.GetInstanceID()) ? f : null;
        }
    }
}
