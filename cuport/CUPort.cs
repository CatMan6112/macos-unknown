// CUPort.dll, mac startup fixes for C:U. gets in through ScriptingAssemblies.json
// and RuntimeInitializeOnLoads.json so the game code stays untouched
//
// settings.json from a retina or windows build can save a size bigger than this
// screen, so the window opens half off screen or fullscreen renders way too many
// pixels. once the screen settles this clamps the size and applies it once
//
// window mode switching is fine as long as allowFullscreenSwitch is on (build.py
// does it). without it the NSWindow gets stuck in fullscreen every fucking time
//
// grep Player.log for [CUPort]. CUPORT_NOFIX=1 logs, and doesnt touch anything.
// CUPORT_TEST="4:Windowed:1280x720;9:FullScreenWindow:1512x982" fakes options menu
// SetResolution calls at those seconds
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using UnityEngine;

namespace CUPort
{
    public static class Boot
    {
        public static void Init()
        {
            var go = new GameObject("CUPort");
            go.hideFlags = HideFlags.HideAndDontSave;
            UnityEngine.Object.DontDestroyOnLoad(go);
            go.AddComponent<WindowFix>();
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
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern CGRect SendRect(IntPtr o, IntPtr sel);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern CGRect SendRect(IntPtr o, IntPtr sel, CGRect r);
        [DllImport(ObjC, EntryPoint = "objc_msgSend")] static extern void SetFrame(IntPtr o, IntPtr sel, CGRect r, bool display, bool animate);

        const ulong FullScreenMask = 1 << 14;  // NSWindowStyleMaskFullScreen

        static IntPtr S(string n) { return sel_registerName(n); }

        // the real one is PlayerWindow, the rest are appkit fullscreen junk.
        // cant use mainWindow, its nil when the app is in the background
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

        public static bool InNativeFullScreen()
        {
            IntPtr w = Window();
            return w != IntPtr.Zero && ((ulong)Send(w, S("styleMask")) & FullScreenMask) != 0;
        }

        // biggest the content can get, screen minus menu bar, dock and title bar
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

        // SetResolution leaves a too big window hanging off screen, so just set
        // the frame ourselves, centered, no zoom animation
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
        // in points, same as the window
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

        // what the game applied from settings.json, clamped to fit
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
}
