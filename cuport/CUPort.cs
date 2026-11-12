// CUPort.dll has the mac startup fixes for C:U. it gets in through ScriptingAssemblies.json
// and RuntimeInitializeOnLoads.json so the game code stays untouched
//
// settings.json from a retina or windows build can save a size bigger than this
// screen so the window opens half off screen or fullscreen renders way too many
// pixels. once the screen settles this clamps the size and applies it once
//
// window mode switching is fine as long as allowFullscreenSwitch is on (build.py
// does it). without it the NSWindow gets stuck in fullscreen every fucking time
//
// grep Player.log for [CUPort]. CUPORT_NOFIX=1 only logs and doesnt touch anything
// CUPORT_TEST set to 4:Windowed:1280x720;9:FullScreenWindow:1512x982 fakes options
// menu SetResolution calls at those seconds
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using UnityEngine;

namespace CUPort
{
    public static class Boot
    {
        public static void Init()
        {
            if (ModGuard.Blocked())
                return;
            var go = new GameObject("CUPort");
            go.hideFlags = HideFlags.HideAndDontSave;
            UnityEngine.Object.DontDestroyOnLoad(go);
            go.AddComponent<WindowFix>();

            var saver = new GameObject("CUPortPauseSaver");
            saver.hideFlags = HideFlags.HideAndDontSave;
            UnityEngine.Object.DontDestroyOnLoad(saver);
            saver.AddComponent<PauseSaver>();

            if (MacMods.On())
            {
                var mods = new GameObject("CUPortMacMods");
                mods.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(mods);
                mods.AddComponent<TouchpadInventory>();
            }

            if (Environment.GetEnvironmentVariable("CUPORT_NOUPDATE") != "1")
            {
                var upd = new GameObject("CUPortUpdateCheck");
                upd.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(upd);
                upd.AddComponent<UpdateCheck>();
            }
        }
    }

    // the launchers MacOS mods box. read from launcher.json at startup so flipping it only needs a relaunch
    // on unless the box says false and CUPORT_MACMODS=0 or 1 beats the file for tests
    static class MacMods
    {
        public static bool On()
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
    }

    // with the launcher's mod box off the app is signed so dyld drops injected
    // libraries. this catches a loader that got in some other way, like a dll
    // added to ScriptingAssemblies.json, and closes the game before it runs.
    // cuport.json says "mods": true when the box is on
    static class ModGuard
    {
        static readonly string[] Loaders = { "BepInEx", "0Harmony", "HarmonyX", "MelonLoader", "MonoMod", "Doorstop" };

        static bool Allowed()
        {
            try
            {
                var json = File.ReadAllText(Path.Combine(Application.dataPath, "Resources/cuport.json"));
                return Regex.IsMatch(json, "\"mods\"\\s*:\\s*true");
            }
            catch (Exception)
            {
                return false;
            }
        }

        static bool IsLoader(Assembly a)
        {
            var name = a.GetName().Name;
            foreach (var l in Loaders)
                if (name.StartsWith(l, StringComparison.OrdinalIgnoreCase))
                    return true;
            return false;
        }

        static bool stopping;

        static void Stop(Assembly a)
        {
            if (stopping)
                return;
            stopping = true;
            Debug.LogError("[CUPort] mod loader " + a.GetName().Name + " found with mods turned off, quitting");
            // Application.Quit waits for the frame to end and a plugin can run in that time
            _exit(1);
        }

        [DllImport("libc")]
        static extern void _exit(int code);

        public static bool Blocked()
        {
            if (Allowed())
                return false;
            AppDomain.CurrentDomain.AssemblyLoad += (_, e) => { if (IsLoader(e.LoadedAssembly)) Stop(e.LoadedAssembly); };
            foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
                if (IsLoader(a))
                {
                    Stop(a);
                    return true;
                }
            return false;
        }
    }

    // raw objc runtime calls to get at the game's NSWindow
    static class Cocoa
    {
        const string ObjC = "/usr/lib/libobjc.A.dylib";
        [StructLayout(LayoutKind.Sequential)] struct CGRect { public double x, y, w, h; }
        [DllImport(ObjC)] static extern IntPtr objc_getClass(string name);
        [DllImport(ObjC)] static extern IntPtr sel_registerName(string name);
        [DllImport(ObjC)] static extern IntPtr object_getClassName(IntPtr o);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern IntPtr Send(IntPtr o, IntPtr sel);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern IntPtr Send(IntPtr o, IntPtr sel, IntPtr a);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern CGRect SendRectArm(IntPtr o, IntPtr sel);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern CGRect SendRectArm(IntPtr o, IntPtr sel, CGRect r);
        // intel returns big structs through a hidden pointer so rects need objc_msgSend_stret
        // plain objc_msgSend crashes there as soon as the window gets clamped. arm64 has no stret
        [DllImport(ObjC, EntryPoint = "objc_msgSend_stret")] static extern CGRect SendRectIntel(IntPtr o, IntPtr sel);
        [DllImport(ObjC, EntryPoint = "objc_msgSend_stret")] static extern CGRect SendRectIntel(IntPtr o, IntPtr sel, CGRect r);
        static readonly bool Intel = RuntimeInformation.ProcessArchitecture == Architecture.X64;
        static CGRect SendRect(IntPtr o, IntPtr sel) { return Intel ? SendRectIntel(o, sel) : SendRectArm(o, sel); }
        static CGRect SendRect(IntPtr o, IntPtr sel, CGRect r) { return Intel ? SendRectIntel(o, sel, r) : SendRectArm(o, sel, r); }
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern void SetFrame(IntPtr o, IntPtr sel, CGRect r, bool display, bool animate);

        const ulong FullScreenMask = 1 << 14;  // NSWindowStyleMaskFullScreen

        static IntPtr S(string n) { return sel_registerName(n); }

        // the real one is PlayerWindow and the rest are appkit fullscreen junk
        // cant use mainWindow cause its nil when the app is in the background
        static IntPtr Window()
        {
            IntPtr app = Send(objc_getClass("NSApplication"), S("sharedApplication"));
            if (app == IntPtr.Zero) return IntPtr.Zero;
            IntPtr list = Send(app, S("windows"));
            int n = (int)Send(list, S("count"));
            for (int i = 0; i < n; i++)
            {
                IntPtr w = Send(list, S("objectAtIndex:"), (IntPtr)i);
                if (Marshal.PtrToStringAnsi(object_getClassName(w)).EndsWith("PlayerWindow")) return w;
            }
            return IntPtr.Zero;
        }

        public static bool Minimized()
        {
            IntPtr w = Window();
            return w != IntPtr.Zero && Send(w, S("isMiniaturized")) != IntPtr.Zero;
        }

        public static bool InNativeFullScreen()
        {
            IntPtr w = Window();
            return w != IntPtr.Zero && ((ulong)Send(w, S("styleMask")) & FullScreenMask) != 0;
        }

        // biggest the content can get after the menu bar dock and title bar
        public static bool MaxContent(out int width, out int height)
        {
            width = height = 0;
            IntPtr w = Window();
            if (w == IntPtr.Zero) return false;
            IntPtr screen = Send(w, S("screen"));
            if (screen == IntPtr.Zero) return false;
            CGRect vis = SendRect(screen, S("visibleFrame"));
            CGRect frame = SendRect(w, S("frame"));
            CGRect content = SendRect(w, S("contentRectForFrameRect:"), frame);
            width = (int)vis.w;
            height = (int)(vis.h - (frame.h - content.h));
            return width > 0 && height > 0;
        }

        // SetResolution leaves a too big window hanging off screen so just set
        // the frame ourselves centered with no zoom animation
        public static bool Resize(int width, int height)
        {
            IntPtr w = Window();
            if (w == IntPtr.Zero) return false;
            IntPtr screen = Send(w, S("screen"));
            if (screen == IntPtr.Zero) return false;
            CGRect vis = SendRect(screen, S("visibleFrame"));
            CGRect frame = SendRect(w, S("frame"));
            CGRect content = SendRect(w, S("contentRectForFrameRect:"), frame);
            double fw = Math.Min(width, vis.w), fh = Math.Min(height + frame.h - content.h, vis.h);
            var r = new CGRect { w = fw, h = fh,
                x = vis.x + Math.Floor((vis.w - fw) / 2), y = vis.y + Math.Floor((vis.h - fh) / 2) };
            SetFrame(w, S("setFrame:display:animate:"), r, true, false);
            return true;
        }
    }

    // reads steams appinfo.vdf cache. steam keeps it fresh so a finder launch still sees updates
    // same parser as patcher/cupatch/steaminfo.py so change both
    static class AppInfo
    {
        const uint V28 = 0x07564428, V29 = 0x07564429;
        const int EntryHead = 4 + 4 + 8 + 20 + 4 + 20;  // state/updated/token/sha1/change/sha1

        public static string DefaultPath()
        {
            return Environment.GetEnvironmentVariable("CUPORT_APPINFO") ?? Path.Combine(
                Environment.GetEnvironmentVariable("HOME") ?? "", "Library/Application Support/Steam/appcache/appinfo.vdf");
        }

        class Reader
        {
            readonly byte[] d;
            readonly string[] keys;
            int p;
            public Reader(byte[] data, int pos, string[] k) { d = data; p = pos; keys = k; }

            string CStr()
            {
                int end = Array.IndexOf(d, (byte)0, p);
                string s = System.Text.Encoding.UTF8.GetString(d, p, end - p);
                p = end + 1;
                return s;
            }

            string Key()
            {
                if (keys == null) return CStr();
                int i = (int)BitConverter.ToUInt32(d, p);
                p += 4;
                return keys[i];
            }

            public Dictionary<string, object> Section()
            {
                var o = new Dictionary<string, object>();
                while (true)
                {
                    byte t = d[p++];
                    if (t == 8) return o;
                    string k = Key();
                    if (t == 0) o[k] = Section();
                    else if (t == 1) o[k] = CStr();
                    else if (t == 2 || t == 4 || t == 6) { o[k] = BitConverter.ToInt32(d, p); p += 4; }
                    else if (t == 7 || t == 10) { o[k] = BitConverter.ToUInt64(d, p); p += 8; }
                    else throw new InvalidDataException("appinfo kv type " + t);
                }
            }
        }

        static object Get(object o, string key)
        {
            var dict = o as Dictionary<string, object>;
            object v = null;
            return dict != null && dict.TryGetValue(key, out v) ? v : null;
        }

        // public manifest gid for the depot or null if steam doesnt know
        public static string PublicManifest(string path, uint appid, uint depot)
        {
            byte[] d = File.ReadAllBytes(path);
            uint magic = BitConverter.ToUInt32(d, 0);
            string[] keys = null;
            int p;
            if (magic == V29)
            {
                int table = (int)BitConverter.ToInt64(d, 8);
                keys = new string[BitConverter.ToUInt32(d, table)];
                int q = table + 4;
                for (int i = 0; i < keys.Length; i++)
                {
                    int end = Array.IndexOf(d, (byte)0, q);
                    keys[i] = System.Text.Encoding.UTF8.GetString(d, q, end - q);
                    q = end + 1;
                }
                p = 16;
            }
            else if (magic == V28) p = 8;
            else return null;

            while (p + 8 <= d.Length)
            {
                uint aid = BitConverter.ToUInt32(d, p), size = BitConverter.ToUInt32(d, p + 4);
                if (aid == 0) return null;
                if (aid == appid)
                {
                    object info = new Reader(d, p + 8 + EntryHead, keys).Section();
                    info = Get(info, "appinfo") ?? info;
                    object m = Get(Get(Get(Get(info, "depots"), depot.ToString()), "manifests"), "public");
                    // newer caches nest gid/size/download and older ones only have the gid
                    object gid = m is string ? m : Get(m, "gid");
                    return gid == null ? null : gid.ToString();
                }
                p += 8 + (int)size;
            }
            return null;
        }
    }

    // native NSAlert through objc. blocks the frame til its answered
    static class Alert
    {
        const string ObjC = "/usr/lib/libobjc.A.dylib";
        [DllImport(ObjC)] static extern IntPtr objc_getClass(string name);
        [DllImport(ObjC)] static extern IntPtr sel_registerName(string name);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern IntPtr Send(IntPtr o, IntPtr sel);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern IntPtr Send(IntPtr o, IntPtr sel, IntPtr a);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern IntPtr SendBool(IntPtr o, IntPtr sel, bool a);

        static IntPtr S(string n) { return sel_registerName(n); }

        static IntPtr NSString(string s)
        {
            byte[] b = System.Text.Encoding.UTF8.GetBytes(s + "\0");
            var h = GCHandle.Alloc(b, GCHandleType.Pinned);
            try { return Send(objc_getClass("NSString"), S("stringWithUTF8String:"), h.AddrOfPinnedObject()); }
            finally { h.Free(); }
        }

        // true when the first button got picked
        public static bool Ask(string title, string body, string yes, string no)
        {
            IntPtr app = Send(objc_getClass("NSApplication"), S("sharedApplication"));
            SendBool(app, S("activateIgnoringOtherApps:"), true);
            IntPtr a = Send(Send(objc_getClass("NSAlert"), S("alloc")), S("init"));
            Send(a, S("setMessageText:"), NSString(title));
            Send(a, S("setInformativeText:"), NSString(body));
            Send(a, S("addButtonWithTitle:"), NSString(yes));
            Send(a, S("addButtonWithTitle:"), NSString(no));
            long r = (long)Send(a, S("runModal"));
            Send(a, S("release"));
            return r == 1000;  // NSAlertFirstButtonReturn
        }
    }

    // finder launches skip the launcher so nothing notices a steam update. lobbies kick old builds on the hash check
    // CUPORT_NOUPDATE=1 turns it off and CUPORT_APPINFO points at a test appinfo.vdf
    public class UpdateCheck : MonoBehaviour
    {
        const float WaitSeconds = 5f;  // let the window fix and the menu settle first
        const string LauncherId = "dev.catman6112.macos-unknown";

        string built, latest;

        static void Log(string msg)
        {
            Debug.Log("[CUPort] " + msg);
        }

        void Start()
        {
            try
            {
                var json = File.ReadAllText(Path.Combine(Application.dataPath, "Resources/cuport.json"));
                var ma = Regex.Match(json, "\"appid\"\\s*:\\s*(\\d+)");
                var mm = Regex.Match(json, "\"manifest\"\\s*:\\s*\"(\\d+)\"");
                if (!ma.Success || !mm.Success)
                {
                    Log("update check: build has no manifest, skipping");
                    Destroy(gameObject);
                    return;
                }
                uint appid = uint.Parse(ma.Groups[1].Value);
                built = mm.Groups[1].Value;
                // windows depot is one id above the app for both editions (EDITIONS in launcher.py)
                latest = AppInfo.PublicManifest(AppInfo.DefaultPath(), appid, appid + 1);
                Log("update check: built " + built + ", steam public " + (latest ?? "unknown"));
                if (latest == null || latest == built)
                    Destroy(gameObject);
            }
            catch (Exception e)
            {
                Log("update check failed: " + e.Message);
                Destroy(gameObject);
            }
        }

        void Update()
        {
            if (Time.realtimeSinceStartup < WaitSeconds || !Application.isFocused)
                return;
            enabled = false;
            bool yes = Alert.Ask("Casualties: Unknown has an update",
                "This copy is an older build than the one on Steam.",
                "Update", "Not now");
            Log("update check: player picked " + (yes ? "update" : "not now"));
            if (yes && OpenLauncher())
                Application.Quit();
            Destroy(gameObject);
        }

        static bool OpenLauncher()
        {
            // bundle id finds the launcher anywhere. the name is for a copy launch services hasnt registered yet
            foreach (var args in new[] { "-b " + LauncherId, "-a \"MacOS Unknown\"" })
            {
                try
                {
                    var p = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(
                        "/usr/bin/open", args + " --args --update") { UseShellExecute = false });
                    p.WaitForExit(5000);
                    if (p.HasExited && p.ExitCode == 0)
                        return true;
                }
                catch (Exception e)
                {
                    Log("update check: open " + args + " failed: " + e.Message);
                }
            }
            Log("update check: launcher not found");
            return false;
        }
    }

    public class WindowFix : MonoBehaviour
    {
        const float StableSeconds = 1.0f;  // screen has to sit still this long to count as settled
        const float HoldSeconds = 1.5f;  // and a match has to stick this long
        const int MaxTries = 3;
        const float LogSeconds = 8f;
        const float GiveUpSeconds = 20f;

        string last;
        float start, stableSince;
        int tries;
        bool finished, matched, noFix, haveTarget;
        int tw, th;
        FullScreenMode tmode;
        string[] test;
        int testStep;

        static void Log(string msg)
        {
            Debug.Log("[CUPort] " + msg);
        }

        static string State()
        {
            return string.Format("frame {0} t {1:0.00} mode {2} size {3}x{4} desktop {5}x{6}{7}",
                Time.frameCount, Time.realtimeSinceStartup, Screen.fullScreenMode,
                Screen.width, Screen.height,
                Screen.currentResolution.width, Screen.currentResolution.height,
                Screen.fullScreenMode == FullScreenMode.Windowed && Cocoa.InNativeFullScreen()
                    ? " (window stuck in native full screen)" : "");
        }

        // same list the game pulls its default size from. retina off means its
        // in points like the window
        static Resolution Largest()
        {
            Resolution[] all = Screen.resolutions;
            return all.Length > 0 ? all[all.Length - 1] : Screen.currentResolution;
        }

        void Awake()
        {
            start = Time.realtimeSinceStartup;
            noFix = Environment.GetEnvironmentVariable("CUPORT_NOFIX") == "1";
            string e = Environment.GetEnvironmentVariable("CUPORT_TEST");
            test = string.IsNullOrEmpty(e) ? new string[0] : e.Split(';');
            Log("start " + State() + (noFix ? " (log only)" : ""));
        }

        void Update()
        {
            float t = Time.realtimeSinceStartup - start;
            string now = string.Format("{0} {1}x{2}", Screen.fullScreenMode, Screen.width, Screen.height);
            if (now != last)
            {
                Log("change " + State());
                last = now;
                stableSince = t;
                matched = false;
            }

            if (!finished && Time.frameCount > 10 && t - stableSince >= StableSeconds)
                Check(t);

            RunTest(t);
            if (testStep < test.Length || (test.Length > 0 && t < 20f)) return;
            if ((finished && t > LogSeconds) || t > GiveUpSeconds)
            {
                Log((finished ? "done " : "screen never settled; leaving it alone ") + State());
                Destroy(gameObject);
            }
        }

        void Check(float t)
        {
            if (!haveTarget && !LoadTarget())
            {
                finished = true;
                return;
            }
            if (Screen.fullScreenMode == tmode && Screen.width == tw && Screen.height == th)
            {
                if (!matched) Log("matches " + State());
                matched = true;
                if (t - stableSince >= HoldSeconds) finished = true;
                return;
            }
            if (noFix || tries >= MaxTries)
            {
                Log(string.Format("want {0} {1}x{2}; {3} {4}", tmode, tw, th,
                    noFix ? "log only" : "giving up", State()));
                finished = true;
                return;
            }
            tries++;
            stableSince = t;
            if (tmode == FullScreenMode.Windowed && Screen.fullScreenMode == FullScreenMode.Windowed
                && !Cocoa.InNativeFullScreen())
            {
                Log(string.Format("try {0}: resize window to {1}x{2}", tries, tw, th));
                if (Cocoa.Resize(tw, th)) return;
            }
            Log(string.Format("try {0}: SetResolution {1}x{2} {3}", tries, tw, th, tmode));
            Screen.SetResolution(tw, th, tmode);
        }

        // what the game applied from settings.json clamped to fit
        bool LoadTarget()
        {
            string path = Path.Combine(Application.persistentDataPath, "settings.json");
            if (!File.Exists(path))
            {
                Log("no settings.json yet; game defaults stand");
                return false;
            }
            string text;
            try { text = File.ReadAllText(path); }
            catch (Exception e) { Log("cannot read settings.json: " + e.Message); return false; }

            int w = ReadInt(text, "reswidth", Screen.width);
            int h = ReadInt(text, "resheight", Screen.height);
            bool full = ReadBool(text, "fullscreen", true);
            tmode = full ? FullScreenMode.FullScreenWindow : FullScreenMode.Windowed;

            int mw, mh;
            if (full || !Cocoa.MaxContent(out mw, out mh))
            {
                Resolution max = Largest();
                mw = max.width; mh = max.height;
            }
            if (mw > 0 && mh > 0 && (w > mw || h > mh))
            {
                float s = Math.Min((float)mw / w, (float)mh / h);
                Log(string.Format("saved size {0}x{1} does not fit {2}x{3}", w, h, mw, mh));
                w = Math.Min(mw, (int)Math.Round(w * s));
                h = Math.Min(mh, (int)Math.Round(h * s));
            }
            tw = w; th = h;
            haveTarget = true;
            return true;
        }

        void RunTest(float t)
        {
            if (testStep >= test.Length) return;
            string[] f = test[testStep].Split(':');
            if (t < float.Parse(f[0])) return;
            string[] wh = f[2].Split('x');
            var mode = (FullScreenMode)Enum.Parse(typeof(FullScreenMode), f[1]);
            Log("test: SetResolution " + f[2] + " " + mode);
            Screen.SetResolution(int.Parse(wh[0]), int.Parse(wh[1]), mode);
            testStep++;
        }

        static string Raw(string text, string name)
        {
            var m = Regex.Match(text, "\"name\"\\s*:\\s*\"" + name + "\"\\s*,\\s*\"value\"\\s*:\\s*([^,}\\s]+)");
            return m.Success ? m.Groups[1].Value : null;
        }

        static int ReadInt(string text, string name, int fallback)
        {
            int v;
            string r = Raw(text, name);
            return r != null && int.TryParse(r, out v) ? v : fallback;
        }

        static bool ReadBool(string text, string name, bool fallback)
        {
            string r = Raw(text, name);
            if (r == "true") return true;
            if (r == "false") return false;
            return fallback;
        }
    }

    // pause only sets timeScale to 0 so the world kept rendering at 120 fps behind a black menu
    // this drops to 30 once the menu is open and 10 when minimized. unpause puts the players vsync and cap back
    //
    // minimizing pauses the game first. CUPORT_NOSAVER=1 turns it all off and CUPORT_NOTHROTTLE=1 only skips the fps drop
    public class PauseSaver : MonoBehaviour
    {
        const int PausedFps = 30;
        const int BackgroundFps = 10;  // paused and minimized or unfocused
        const float CheckSeconds = 0.25f;

        Type handler, settings;
        FieldInfo mainField, progressField, settingsField;
        MethodInfo toggle;
        bool lookedUp, throttled, wasMinimized, noThrottle;
        int savedVsync, savedFps, setFps;
        float nextCheck;

        void Awake()
        {
            if (Environment.GetEnvironmentVariable("CUPORT_NOSAVER") == "1") enabled = false;
            noThrottle = Environment.GetEnvironmentVariable("CUPORT_NOTHROTTLE") == "1";
        }

        // game types live in Assembly-CSharp which this dll doesnt reference
        bool LookUp()
        {
            if (lookedUp) return handler != null;
            lookedUp = true;
            handler = Type.GetType("PauseHandler, Assembly-CSharp");
            settings = Type.GetType("SettingsMenu, Assembly-CSharp");
            if (handler == null) { Debug.Log("[CUPort] no PauseHandler; pause saver off"); return false; }
            const BindingFlags F = BindingFlags.Public | BindingFlags.Static | BindingFlags.Instance;
            mainField = handler.GetField("main", F);
            progressField = handler.GetField("pauseProgress", F);
            toggle = handler.GetMethod("TogglePause", BindingFlags.Public | BindingFlags.Static);
            if (settings != null) settingsField = settings.GetField("instance", F);
            if (mainField == null || progressField == null || toggle == null)
            {
                Debug.Log("[CUPort] PauseHandler changed shape; pause saver off");
                handler = null;
                return false;
            }
            return true;
        }

        void Update()
        {
            if (Time.unscaledTime < nextCheck) return;
            nextCheck = Time.unscaledTime + CheckSeconds;
            if (!LookUp()) { Release(); enabled = false; return; }

            // cast first or a destroyed main doesnt read as null
            var main = mainField.GetValue(null) as UnityEngine.Object;
            bool inWorld = main != null;
            bool paused = inWorld && (bool)handler.GetField("isPaused").GetValue(main);
            bool open = paused && (float)progressField.GetValue(main) >= 1f;
            bool settingsOpen = settingsField != null && settingsField.GetValue(null) as UnityEngine.Object != null;

            bool minimized = Cocoa.Minimized();
            if (minimized && !wasMinimized && inWorld && !paused)
            {
                Debug.Log("[CUPort] minimized; pausing");
                toggle.Invoke(null, null);  // game says no during death screens and worldgen
            }
            wasMinimized = minimized;

            if (open && !settingsOpen && !noThrottle)
                Hold(minimized || !Application.isFocused ? BackgroundFps : PausedFps);
            else
                Release();
        }

        void Hold(int fps)
        {
            if (!throttled)
            {
                savedVsync = QualitySettings.vSyncCount;
                savedFps = Application.targetFrameRate;
                throttled = true;
                Debug.Log(string.Format("[CUPort] paused; {0} fps (was vsync {1} cap {2})", fps, savedVsync, savedFps));
            }
            else if (QualitySettings.vSyncCount != 0 || Application.targetFrameRate != setFps)
            {
                // game or console changed them while held so those win on unpause
                if (QualitySettings.vSyncCount != 0) savedVsync = QualitySettings.vSyncCount;
                if (Application.targetFrameRate != setFps) savedFps = Application.targetFrameRate;
            }
            setFps = fps;
            QualitySettings.vSyncCount = 0;
            Application.targetFrameRate = fps;
        }

        void Release()
        {
            if (!throttled) return;
            throttled = false;
            QualitySettings.vSyncCount = savedVsync;
            Application.targetFrameRate = savedFps;
            Debug.Log(string.Format("[CUPort] unpaused; vsync {0} cap {1}", savedVsync, savedFps));
        }
    }

    // trackpad clicks have NSEvent subtype 3 (touch) and mouse clicks have 0. unity cant see it so
    // an NSEvent local monitor catches the click before any Update and the swap lands on that same click
    static class ClickSource
    {
        const string ObjC = "/usr/lib/libobjc.A.dylib";
        const ulong LeftDownMask = 1 << 1, RightDownMask = 1 << 3;
        const int SubtypeTouch = 3;

        [DllImport(ObjC)] static extern IntPtr objc_getClass(string name);
        [DllImport(ObjC)] static extern IntPtr sel_registerName(string name);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern IntPtr Send(IntPtr o, IntPtr sel);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern IntPtr AddMonitor(IntPtr o, IntPtr sel, ulong mask, IntPtr block);
        [DllImport("/usr/lib/libSystem.B.dylib")] static extern IntPtr dlsym(IntPtr handle, string name);

        // NSEvent *(^)(NSEvent *) as a plain function. the block pointer comes first
        delegate IntPtr Handler(IntPtr block, IntPtr ev);

        static Handler keep;  // the gc must never collect this while appkit holds the pointer
        static IntPtr subtypeSel;
        static Action<bool> onClick;

        // a global block is this struct. appkit never copies or frees it so one allocation for the whole process is fine
        public static bool Watch(Action<bool> clicked)
        {
            IntPtr isa = dlsym(new IntPtr(-2), "_NSConcreteGlobalBlock");  // -2 is RTLD_DEFAULT
            if (isa == IntPtr.Zero) return false;
            onClick = clicked;
            subtypeSel = sel_registerName("subtype");
            keep = Invoke;

            IntPtr desc = Marshal.AllocHGlobal(16);
            Marshal.WriteInt64(desc, 0, 0);  // reserved
            Marshal.WriteInt64(desc, 8, 32);  // size of the block
            IntPtr block = Marshal.AllocHGlobal(32);
            Marshal.WriteIntPtr(block, 0, isa);
            Marshal.WriteInt32(block, 8, 1 << 28);  // BLOCK_IS_GLOBAL
            Marshal.WriteInt32(block, 12, 0);
            Marshal.WriteIntPtr(block, 16, Marshal.GetFunctionPointerForDelegate(keep));
            Marshal.WriteIntPtr(block, 24, desc);

            IntPtr monitor = AddMonitor(objc_getClass("NSEvent"),
                sel_registerName("addLocalMonitorForEventsMatchingMask:handler:"), LeftDownMask | RightDownMask, block);
            return monitor != IntPtr.Zero;
        }

        static IntPtr Invoke(IntPtr block, IntPtr ev)
        {
            // an exception getting back into appkit takes the whole game down
            try
            {
                int sub = (int)((long)Send(ev, subtypeSel) & 0xffff);
                onClick(sub == SubtypeTouch);
            }
            catch (Exception e)
            {
                Debug.Log("[CUPort] touchpad: click callback failed: " + e.Message);
            }
            return ev;
        }
    }

    // inventory drag is on right click so a trackpad needs two finger clicks. a trackpad click swaps it with attack
    // only cachedBinds changes so it never saves. no swap mid drag or the item sticks. off for pour dial/minigames/pause
    public class TouchpadInventory : MonoBehaviour
    {
        const string Interact = "iteminteract", Attack = "attack";

        Dictionary<string, KeyCode> binds;
        FieldInfo cameraMain, radialOpen, woundView, liquid, minigameMain, minigameCurrent;
        PropertyInfo paused;
        bool swapped, logged, open, idle;
        KeyCode oldInteract, oldAttack, newAttack;

        static void Log(string msg)
        {
            Debug.Log("[CUPort] touchpad: " + msg);
        }

        void Start()
        {
            const BindingFlags S = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;
            const BindingFlags I = BindingFlags.Public | BindingFlags.Instance;
            Type keyBinds = Type.GetType("KeyBinds, Assembly-CSharp");
            Type camera = Type.GetType("PlayerCamera, Assembly-CSharp");
            Type minigame = Type.GetType("MinigameBase, Assembly-CSharp");
            Type liquidType = Type.GetType("LiquidTransfer, Assembly-CSharp");
            Type pause = Type.GetType("PauseHandler, Assembly-CSharp");
            if (keyBinds != null)
            {
                var f = keyBinds.GetField("cachedBinds", S);
                if (f != null) binds = f.GetValue(null) as Dictionary<string, KeyCode>;
            }
            if (camera != null)
            {
                cameraMain = camera.GetField("main", S);
                radialOpen = camera.GetField("radialOpen", I);
                woundView = camera.GetField("woundView", I);
            }
            if (minigame != null)
            {
                minigameMain = minigame.GetField("main", S);
                minigameCurrent = minigame.GetField("currentMinigame", I);
            }
            if (liquidType != null) liquid = liquidType.GetField("instance", S);
            if (pause != null) paused = pause.GetProperty("paused", S);
            if (binds == null || cameraMain == null || radialOpen == null)
            {
                Log("game changed shape; off");
                enabled = false;
                return;
            }
            if (!ClickSource.Watch(Clicked))
            {
                Log("no click monitor; off");
                enabled = false;
                return;
            }
            Log("watching clicks");
        }

        static bool Alive(FieldInfo f, object owner)
        {
            return f != null && f.GetValue(owner) as UnityEngine.Object != null;
        }

        bool InInventory()
        {
            object cam = cameraMain.GetValue(null) as UnityEngine.Object;
            if (cam == null) return false;
            var wound = woundView != null ? woundView.GetValue(cam) as GameObject : null;
            if (!(bool)radialOpen.GetValue(cam) && !(wound != null && wound.activeSelf)) return false;
            if (paused != null && (bool)paused.GetValue(null, null)) return false;
            if (Alive(liquid, null)) return false;
            var mg = minigameMain != null ? minigameMain.GetValue(null) as UnityEngine.Object : null;
            if (mg != null && Alive(minigameCurrent, mg)) return false;
            return true;
        }

        // held or let go this frame. GetKeyDown already counts as held
        static bool MouseBusy()
        {
            return Input.GetKey(KeyCode.Mouse0) || Input.GetKey(KeyCode.Mouse1)
                || Input.GetKeyUp(KeyCode.Mouse0) || Input.GetKeyUp(KeyCode.Mouse1);
        }

        static KeyCode Get(Dictionary<string, KeyCode> d, string k)
        {
            KeyCode v;
            return d.TryGetValue(k, out v) ? v : KeyCode.None;
        }

        // the settings menu re caches binds when you change one. if ours got
        // overwritten theres nothing to put back
        void CheckOwned()
        {
            if (swapped && (Get(binds, Interact) != KeyCode.Mouse0 || Get(binds, Attack) != newAttack))
                swapped = false;
        }

        // late so every game Update this frame already read the binds. the click
        // callback runs before the next frame and uses what this saw
        void LateUpdate()
        {
            CheckOwned();
            open = InInventory();
            idle = !MouseBusy();
            if (swapped && !open && idle) Restore();
        }

        // ClickSource calls this on every mouse down before the game sees it
        void Clicked(bool trackpad)
        {
            if (!enabled || !idle) return;
            CheckOwned();
            if (trackpad && open && !swapped) Swap();
            else if (!trackpad && swapped) Restore();
        }

        void Swap()
        {
            oldInteract = Get(binds, Interact);
            oldAttack = Get(binds, Attack);
            if (oldInteract == KeyCode.Mouse0 || oldInteract == KeyCode.None) return;  // nothing to fix
            newAttack = oldAttack == KeyCode.Mouse0 ? oldInteract : oldAttack;
            binds[Interact] = KeyCode.Mouse0;
            binds[Attack] = newAttack;
            swapped = true;
            if (!logged)
            {
                Log(string.Format("trackpad click; {0} on Mouse0, {1} on {2}", Interact, Attack, newAttack));
                logged = true;
            }
        }

        void Restore()
        {
            binds[Interact] = oldInteract;
            binds[Attack] = oldAttack;
            swapped = false;
        }

        void OnDestroy()
        {
            if (swapped) Restore();
        }
    }
}
