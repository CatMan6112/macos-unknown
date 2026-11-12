#!/usr/bin/env python3 -I
"""
when the dune lowky such a cutie you lowky jus pet
"""

import ctypes, json, os, pathlib, queue, re, shutil, ssl, subprocess, sys, tempfile, threading, time
import urllib.request
import tkinter as tk
import tkinter.font as tkfont

HERE = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE))
from cupatch import build as cubuild  # noqa: E402
from cupatch import mods as modloader  # noqa: E402
from cupatch import steaminfo  # noqa: E402

ASSETS = HERE / "assets"
STEAM = pathlib.Path.home() / "Library/Application Support/Steam"
CONTENT = STEAM / "Steam.AppBundle/Steam/Contents/MacOS/steamapps/content"
CONSOLE_LOG = STEAM / "logs/console_log.txt"
APP = pathlib.Path(os.environ.get("CUPORT_APP", pathlib.Path.home() / "Applications/Casualties Unknown.app"))
EDITIONS = {"full": (cubuild.FULL, 4576491), "demo": (cubuild.DEMO, 4576511)}

W, H = 440, 282
INK, FILL, DIM, LINK = "#000000", "#0000cc", "#a0a0a0", "#0000ee"
SITE = "https://catman6112.dev"

VERSION = "1.2.4"
RELEASES = "https://api.github.com/repos/CatMan6112/macos-unknown/releases/latest"
SETTINGS = pathlib.Path.home() / "Library/Application Support/macos-unknown/launcher.json"
# python.org builds ship without CA certs, every mac has this one
TLS = ssl.create_default_context(cafile="/etc/ssl/cert.pem")

# build log line -> how far the bar jumps when that step starts
STEPS = {"checking engine version": 0.02, "copying the macOS player": 0.06,
         "copying game data": 0.12, "swapping shaders for Metal": 0.30,
         "installing Steam for macOS": 0.86, "installing the startup fix": 0.90,
         "signing": 0.94}


def depot_dir(edition):
    app, depot = EDITIONS[edition]
    return CONTENT / f"app_{app}" / f"depot_{depot}"


def console_lines():
    try:
        return CONSOLE_LOG.read_text(errors="replace").splitlines()
    except OSError:
        return []


def depot_events(depot, since=0):
    # last download state for a depot in steams console log from the since line on
    state = {}
    for line in console_lines()[since:]:
        if f"depot {depot} (" in line and "Downloading" in line:
            m = re.search(r"\((\d+) files", line)
            state = {"files": int(m.group(1)) if m else None}
        elif "Depot download complete" in line and f"depot_{depot}" in line:
            m = re.search(r"manifest (\d+)", line)
            state.update(done=True, manifest=m.group(1) if m else None)
        elif "Depot download failed" in line and f"depot {depot}" in line:
            state = {"failed": "offline" if "No connection" in line else line.split("failed :", 1)[-1].strip()}
    return state


def built_info():
    try:
        return json.loads((APP / "Contents/Resources/cuport.json").read_text())
    except (OSError, ValueError):
        return None


def port_ok():
    # an app from an older launcher has to be rebuilt before it can be played
    info = built_info()
    return bool(info) and info.get("port", 1) >= cubuild.PORT


def load_settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(d):
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(d, indent=1))
    except OSError:
        pass


def untranslocate(app):
    # a quarantined app opened where it was unzipped runs from a read only copy
    # so ask macos where the real one is. None if it wont say
    if "/AppTranslocation/" not in str(app):
        return app
    try:
        cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        sec = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        vp = ctypes.c_void_p
        cf.CFURLCreateFromFileSystemRepresentation.restype = vp
        cf.CFURLCreateFromFileSystemRepresentation.argtypes = [vp, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
        cf.CFURLGetFileSystemRepresentation.restype = ctypes.c_bool
        cf.CFURLGetFileSystemRepresentation.argtypes = [vp, ctypes.c_bool, ctypes.c_char_p, ctypes.c_long]
        cf.CFRelease.argtypes = [vp]
        sec.SecTranslocateCreateOriginalPathForURL.restype = vp
        sec.SecTranslocateCreateOriginalPathForURL.argtypes = [vp, vp]
        raw = str(app).encode()
        url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), True)
        orig = sec.SecTranslocateCreateOriginalPathForURL(url, None) if url else None
        if url:
            cf.CFRelease(url)
        if not orig:
            return None
        buf = ctypes.create_string_buffer(4096)
        ok = cf.CFURLGetFileSystemRepresentation(orig, True, buf, len(buf))
        cf.CFRelease(orig)
        real = pathlib.Path(buf.value.decode()) if ok else None
    except (OSError, AttributeError):
        return None
    return real if real and "/AppTranslocation/" not in str(real) and real.exists() else None


def own_bundle():
    # the .app were running from, only exists once pyinstaller wraps us
    if os.environ.get("CUPORT_SELF"):
        return pathlib.Path(os.environ["CUPORT_SELF"])
    if getattr(sys, "frozen", False):
        app = pathlib.Path(sys.executable).resolve().parents[2]
        if app.suffix == ".app":
            return untranslocate(app) or app
    return None


def ver(tag):
    return tuple(int(n) for n in re.findall(r"\d+", tag))


def fetch(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": "macos-unknown-launcher", "Accept": accept})
    return urllib.request.urlopen(req, timeout=10, context=TLS)


def newer_release():
    # latest release if its newer than us and has a zip on it, otherwise None
    with fetch(RELEASES) as r:
        rel = json.load(r)
    tag = rel.get("tag_name", "")
    zips = [a for a in rel.get("assets", []) if a.get("name", "").endswith(".zip")]
    if not zips or not ver(tag) or ver(tag) <= ver(VERSION):
        return None
    return {"tag": tag, "title": (rel.get("name") or "").strip() or tag,
            "summary": summary(rel.get("body") or ""),
            "url": zips[0]["browser_download_url"], "size": zips[0].get("size") or 0}


def summary(body, cap=300):
    # first paragraph of the release notes without the markdown. long ones get cut so the popup stays small
    para = body.replace("\r", "").strip().split("\n\n")[0]
    para = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", para)
    para = " ".join(para.replace("**", "").replace("`", "").split())
    if len(para) > cap:
        para = para[:cap].rsplit(" ", 1)[0] + ".."
    return para


def install_update(rel, bundle, progress):
    # download the zip, unpack it next to us, then swap the bundles
    if "/AppTranslocation/" in str(bundle) or not os.access(bundle.parent, os.W_OK):
        raise RuntimeError("move the launcher to Applications and open it again")
    work = pathlib.Path(tempfile.mkdtemp(prefix="cuport-update-"))
    zp = work / "update.zip"
    with fetch(rel["url"], accept="application/octet-stream") as r, open(zp, "wb") as f:
        total = int(r.headers.get("Content-Length") or rel["size"] or 0)
        got = 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            got += len(chunk)
            if total:
                progress(0.9 * got / total)
    progress(0.92)
    out = work / "unpacked"
    # ditto keeps the code signature and symlinks intact, zipfile does not
    if subprocess.run(["ditto", "-x", "-k", str(zp), str(out)], capture_output=True).returncode:
        raise RuntimeError("the download was damaged")
    apps = list(out.glob("*.app"))
    if len(apps) != 1:
        raise RuntimeError("the release zip has no app in it")
    progress(0.96)
    # stage on the same disk so the final swap is a plain rename
    staged = bundle.with_name(bundle.stem + ".update.app")
    if staged.exists():
        shutil.move(str(staged), str(pathlib.Path.home() / ".Trash" / f"{staged.stem} {time.strftime('%H%M%S')}.app"))
    shutil.move(str(apps[0]), str(staged))
    old = pathlib.Path.home() / ".Trash" / f"{bundle.stem} {VERSION}.app"
    if old.exists():
        old = old.with_name(f"{bundle.stem} {VERSION} {time.strftime('%H%M%S')}.app")
    shutil.move(str(bundle), str(old))  # old launcher goes to the trash, same as old builds
    try:
        staged.rename(bundle)
    except OSError:
        shutil.move(str(old), str(bundle))
        raise
    shutil.rmtree(work, ignore_errors=True)  # only our own temp folder
    progress(1.0)


FONT = SMALL = BIG = ITALIC = UNDER = None


def make_fonts():
    global FONT, SMALL, BIG, ITALIC, UNDER
    base = tkfont.nametofont("TkDefaultFont")
    SMALL = base.copy()
    FONT = base.copy()
    FONT.configure(weight="bold")
    ITALIC = base.copy()
    ITALIC.configure(slant="italic")
    UNDER = base.copy()
    UNDER.configure(underline=True)
    BIG = base.copy()
    BIG.configure(weight="bold", size=22)


class Button:
    def __init__(self, cv, x, y, w, text, cmd):
        self.cv, self.cmd, self.enabled = cv, cmd, True
        self.box = cv.create_rectangle(x, y, x + w, y + 24, outline=INK, fill="#ffffff")
        self.txt = cv.create_text(x + w / 2, y + 12, text=text, font=FONT, fill=INK)
        for item in (self.box, self.txt):
            cv.tag_bind(item, "<ButtonPress-1>", self.press)
            cv.tag_bind(item, "<ButtonRelease-1>", self.release)

    def press(self, _):
        if self.enabled:
            self.cv.itemconfig(self.box, fill=INK)
            self.cv.itemconfig(self.txt, fill="#ffffff")

    def release(self, _):
        if not self.enabled:
            return
        self.cv.itemconfig(self.box, fill="#ffffff")
        self.cv.itemconfig(self.txt, fill=INK)
        self.cmd()

    def set(self, enabled):
        self.enabled = enabled
        c = INK if enabled else DIM
        self.cv.itemconfig(self.box, outline=c, fill="#ffffff")
        self.cv.itemconfig(self.txt, fill=c)


class Bar:
    BLOCK = 8

    def __init__(self, cv, x, y, w):
        self.cv, self.x, self.y, self.w = cv, x, y, w
        cv.create_rectangle(x, y, x + w, y + 18, outline=INK, fill="#ffffff")
        self.blocks = []
        self.pct = cv.create_text(x + w + 6, y + 9, text="", font=SMALL, fill=INK, anchor="w")
        self.value = 0.0

    def set(self, v):
        v = max(0.0, min(1.0, v))
        self.value = v
        for b in self.blocks:
            self.cv.delete(b)
        n = int((self.w - 4) * v) // self.BLOCK
        self.blocks = [self.cv.create_rectangle(
            self.x + 3 + i * self.BLOCK, self.y + 3,
            self.x + 3 + i * self.BLOCK + self.BLOCK - 2, self.y + 15,
            outline="", fill=FILL) for i in range(n)]
        self.cv.itemconfig(self.pct, text=f"{round(v * 100)}%" if v else "")
        self.cv.tag_raise(self.pct)


class ProgressWindow:
    # pops up over the launcher while something runs like windows does
    PW, PH = 360, 50

    def __init__(self, root, title):
        self.win = win = tk.Toplevel(root, bg="#ffffff")
        win.title(title)
        win.resizable(False, False)
        win.transient(root)
        win.protocol("WM_DELETE_WINDOW", lambda: None)
        cv = tk.Canvas(win, width=self.PW, height=self.PH, bg="#ffffff",
                       highlightthickness=0, bd=0)
        cv.pack()
        self.bar = Bar(cv, 16, 16, self.PW - 70)
        root.update_idletasks()
        x = root.winfo_rootx() + (W - self.PW) // 2
        y = root.winfo_rooty() + (H - self.PH) // 2
        win.geometry(f"+{x}+{y}")

    def set(self, v):
        self.bar.set(v)

    @property
    def value(self):
        return self.bar.value

    def close(self):
        self.win.destroy()


NOTICE = ("Hey! Clicking continue will open steam to download the required windows "
          "file. I know the terminal looks scary but all ya gotta do is click "
          "command + v and enter! I promise! that easy and then you can come back "
          "to the app!! Just one command :D")


class SteamNotice:
    # heads up before the steam console pops open on them
    NW = 380

    def __init__(self, root, on_continue):
        self.on_continue = on_continue
        self.win = win = tk.Toplevel(root, bg="#ffffff")
        win.title("Heads up")
        win.resizable(False, False)
        win.transient(root)
        cv = tk.Canvas(win, width=self.NW, height=10, bg="#ffffff",
                       highlightthickness=0, bd=0)
        cv.pack()
        mid = self.NW / 2
        body = cv.create_text(mid, 20, text=NOTICE, font=SMALL, fill=INK,
                              width=self.NW - 40, justify="center", anchor="n")
        y = cv.bbox(body)[3] + 18
        # last line is three pieces so the word own can be italic
        parts = [("(you do have to.. actually ", SMALL), ("own", ITALIC), (" the game though.)", SMALL)]
        x = mid - sum(f.measure(t) for t, f in parts) / 2
        for t, f in parts:
            cv.create_text(x, y, text=t, font=f, fill=INK, anchor="w")
            x += f.measure(t)
        by = y + 22
        Button(cv, mid - 92, by, 84, "Cancel", self.close)
        Button(cv, mid + 8, by, 84, "Continue", self.go)
        height = by + 24 + 18
        cv.configure(height=height)
        root.update_idletasks()
        win.geometry(f"+{root.winfo_rootx() + (W - self.NW) // 2}"
                     f"+{root.winfo_rooty() + max(0, (H - height) // 2)}")
        win.bind("<Return>", lambda _e: self.go())
        win.bind("<Escape>", lambda _e: self.close())
        win.grab_set()
        win.after(50, lambda: (win.lift(), win.focus_force(), cv.focus_set()))

    def close(self):
        self.win.grab_release()
        self.win.destroy()

    def go(self):
        self.close()
        self.on_continue()


class UpdatePrompt:
    UW = 280

    def __init__(self, root, title, text, on_yes, on_no):
        self.on_yes, self.on_no = on_yes, on_no
        self.win = win = tk.Toplevel(root, bg="#ffffff")
        win.title("Update")
        win.resizable(False, False)
        win.transient(root)
        win.protocol("WM_DELETE_WINDOW", self.no)
        cv = tk.Canvas(win, width=self.UW, height=10, bg="#ffffff",
                       highlightthickness=0, bd=0)
        cv.pack()
        mid = self.UW / 2
        cv.create_text(mid, 32, text="do u wanna update? :3", font=FONT, fill=INK)
        # release title wraps so the buttons go wherever it ends
        name = cv.create_text(mid, 50, text=title, font=SMALL, fill=INK,
                              width=self.UW - 40, justify="center", anchor="n")
        by = cv.bbox(name)[3] + 22
        if text:
            notes = cv.create_text(mid, by - 10, text=text, font=SMALL, fill=INK,
                                   width=self.UW - 40, justify="left", anchor="n")
            by = cv.bbox(notes)[3] + 22
        Button(cv, mid - 92, by, 84, "No", self.no)
        Button(cv, mid + 8, by, 84, "Yes", self.yes)
        height = by + 24 + 18
        cv.configure(height=height)
        root.update_idletasks()
        win.geometry(f"+{root.winfo_rootx() + (W - self.UW) // 2}"
                     f"+{root.winfo_rooty() + (H - height) // 2}")
        win.bind("<Return>", lambda _e: self.yes())
        win.bind("<Escape>", lambda _e: self.no())
        win.grab_set()
        win.after(50, lambda: (win.lift(), win.focus_force(), cv.focus_set()))

    def close(self):
        self.win.grab_release()
        self.win.destroy()

    def yes(self):
        self.close()
        self.on_yes()

    def no(self):
        self.close()
        self.on_no()


class Launcher:
    def __init__(self, root):
        self.root = root
        root.title("MacOS: Unknown")
        root.resizable(False, False)
        root.configure(bg="#ffffff")
        cv = self.cv = tk.Canvas(root, width=W, height=H, bg="#ffffff",
                                 highlightthickness=0, bd=0)
        cv.pack()

        mid = W / 2
        self.logo = tk.PhotoImage(file=str(ASSETS / "logo.png"))
        cv.create_image(mid, 14, image=self.logo, anchor="n")
        cv.create_text(mid, 132, text="MacOS: Unknown", font=BIG, fill=INK)
        cv.create_text(mid, 156, text="Casualties: Unknown for MacOS", fill=INK)

        has_full, has_demo = depot_dir("full").exists(), depot_dir("demo").exists()
        self.edition = "demo" if has_demo and not has_full else "full"
        self.radios = {}
        # edition label and both radios centered as one row
        items = [("label", "Edition", FONT), ("full", "Full game", SMALL), ("demo", "Demo", SMALL)]
        widths = [f.measure(t) + (0 if k == "label" else 18) for k, t, f in items]
        x = mid - (sum(widths) + 20 * (len(items) - 1)) / 2
        y = 186
        for (k, text, f), w in zip(items, widths):
            if k == "label":
                cv.create_text(x, y, text=text, font=f, fill=INK, anchor="w")
            else:
                o = cv.create_oval(x, y - 6, x + 12, y + 6, outline=INK, fill="#ffffff")
                dot = cv.create_oval(x + 3, y - 3, x + 9, y + 3, outline="", fill=INK)
                t = cv.create_text(x + 18, y, text=text, font=f, fill=INK, anchor="w")
                for item in (o, dot, t):
                    cv.tag_bind(item, "<Button-1>", lambda _e, ed=k: self.pick(ed))
                self.radios[k] = dot
            x += w + 20

        self.settings = load_settings()
        self.tick_mark, _ = self.checkbox(14, "Automatic updates", lambda: self.set_auto(not self.auto_update()))
        self.set_auto(self.auto_update())
        self.mods_mark, mods_label = self.checkbox(34, "Mod loader", lambda: self.toggle_mods())
        # opens the BepInEx folder and its only there while the box is ticked
        self.plugins_link = cv.create_text(cv.bbox(mods_label)[2] + 8, 34, text="BepInEx",
                                           font=UNDER, fill=LINK, anchor="w")
        cv.tag_bind(self.plugins_link, "<Button-1>", lambda _e: self.open_plugins())
        cv.tag_bind(self.plugins_link, "<Enter>", lambda _e: cv.configure(cursor="pointinghand"))
        cv.tag_bind(self.plugins_link, "<Leave>", lambda _e: cv.configure(cursor=""))
        self.show_mods()
        # touchpad fixes and such in CUPort.dll. the game reads this from launcher.json
        # when it starts so theres nothing to rebuild
        self.macmods_mark, _ = self.checkbox(54, "MacOS enhancements", lambda: self.set_macmods(not self.macmods_on()))
        self.set_macmods(self.macmods_on())

        bw, gap = 84, 8
        bx = mid - (3 * bw + 2 * gap) / 2
        self.b_files = Button(cv, bx, 208, bw, "Get files", self.get_files)
        self.b_build = Button(cv, bx + bw + gap, 208, bw, "Build", self.start_build)
        self.b_play = Button(cv, bx + 2 * (bw + gap), 208, bw, "Play", self.play)
        self.err = cv.create_text(mid, 240, text="", font=SMALL, fill="#ff0000",
                                  width=W - 40, justify="center", anchor="n")

        self.dune = tk.PhotoImage(file=str(ASSETS / "dune.png"))
        self.dune_id = cv.create_image(-120, H + 6, image=self.dune, anchor="sw")
        cv.tag_lower(self.dune_id)

        link = cv.create_text(W - 8, H - 8, text="catman6112", font=UNDER, fill=LINK, anchor="se")
        cv.create_text(cv.bbox(link)[0], H - 8, text="made by ", font=SMALL, fill=INK, anchor="se")
        cv.tag_bind(link, "<Button-1>", lambda _e: subprocess.run(["open", SITE]))
        cv.tag_bind(link, "<Enter>", lambda _e: cv.configure(cursor="pointinghand"))
        cv.tag_bind(link, "<Leave>", lambda _e: cv.configure(cursor=""))

        self.q = queue.Queue()
        self.busy = None  # download or build while one is going
        self.popup = None
        self.watch_from = 0
        self.creep_to = 0.0
        self.chain = "--update" in sys.argv[1:]
        self.pick(self.edition)
        if self.chain:
            root.after(800, self.resume_update)
        root.after(400, self.slide_dune, 0)
        root.after(200, self.tick)
        self.bundle = own_bundle()
        if self.bundle and self.auto_update():
            threading.Thread(target=self.check_thread, daemon=True).start()

    def checkbox(self, y, text, cmd):
        cv, x = self.cv, 10
        box = cv.create_rectangle(x, y - 6, x + 12, y + 6, outline=INK, fill="#ffffff")
        mark = cv.create_line(x + 3, y, x + 5, y + 3, x + 9, y - 3, fill=INK, width=2)
        label = cv.create_text(x + 18, y, text=text, font=SMALL, fill=INK, anchor="w")
        for item in (box, mark, label):
            cv.tag_bind(item, "<Button-1>", lambda _e: cmd())
        return mark, label

    # state

    def pick(self, ed):
        if self.busy:
            return
        self.edition = ed
        for k, dot in self.radios.items():
            self.cv.itemconfig(dot, state="normal" if k == ed else "hidden")
        self.refresh()

    def depot_ready(self):
        d = depot_dir(self.edition)
        return any(d.glob("*_Data/globalgamemanagers"))

    def depot_manifest(self):
        # whats on disk. steam rotates console_log.txt on restart so launcher.json keeps a copy
        app, depot = EDITIONS[self.edition]
        known = self.settings.setdefault("depots", {})
        m = depot_events(depot).get("manifest")
        if m and known.get(str(depot)) != m:
            known[str(depot)] = m
            save_settings(self.settings)
        if m or known.get(str(depot)):
            return m or known[str(depot)]
        # downloaded before launcher.json kept a record so trust what the build saw
        info = built_info()
        return info.get("manifest") if info and info.get("appid") == app else None

    def latest_manifest(self):
        # what steam says is public right now. offline it falls back to whats on disk
        app, depot = EDITIONS[self.edition]
        return steaminfo.public_manifest(app, depot) or self.depot_manifest()

    def state(self):
        """downloaded/fresh/current. fresh means the depot is the newest build and current means the app is"""
        ready = self.depot_ready()
        latest = self.latest_manifest()
        fresh = ready and (not latest or self.depot_manifest() == latest)
        info = built_info()
        current = bool(info and info.get("appid") == EDITIONS[self.edition][0] and APP.exists()
                       and (not latest or info.get("manifest") == latest) and port_ok())
        return ready, fresh, current

    def refresh(self):
        _ready, fresh, current = self.state()
        idle = not self.busy
        self.b_files.set(idle)
        self.b_build.set(idle and fresh and not current)
        self.b_play.set(idle and APP.exists() and port_ok())

    def resume_update(self):
        # the game opened us with --update so do whatever is left of get files/build/play
        if not self.chain or self.busy or self.popup:
            return
        _ready, fresh, current = self.state()
        if current:
            self.chain = False
            self.play()
        elif fresh:
            self.start_build()
        else:
            self.get_files()

    def open_popup(self, title):
        self.popup = ProgressWindow(self.root, title)

    def close_popup(self):
        if self.popup:
            self.popup.close()
            self.popup = None

    def error(self, msg):
        self.cv.itemconfig(self.err, text=msg)

    # updates

    def auto_update(self):
        return self.settings.get("auto_update", True)

    def set_auto(self, on):
        self.settings["auto_update"] = on
        save_settings(self.settings)
        self.cv.itemconfig(self.tick_mark, state="normal" if on else "hidden")

    def check_thread(self):
        try:
            rel = newer_release()
        except Exception:  # offline or github is down, try again next launch
            return
        if rel:
            self.q.put(("update", rel))

    def offer_update(self, rel):
        if self.busy or self.popup:
            return
        UpdatePrompt(self.root, rel["title"], rel.get("summary", ""), lambda: self.start_update(rel), lambda: self.set_auto(False))

    def start_update(self, rel):
        self.error("")
        self.busy = "update"
        self.open_popup("Update")
        self.refresh()
        threading.Thread(target=self.update_thread, args=(rel,), daemon=True).start()

    def update_thread(self, rel):
        try:
            install_update(rel, self.bundle, lambda v: self.q.put(("uprog", v)))
            self.q.put(("updated", None))
        except Exception as e:
            self.q.put(("upfail", str(e)))

    def on_update_msg(self, kind, msg):
        if kind == "update":
            self.offer_update(msg)
        elif kind == "uprog":
            self.popup.set(msg)
        elif kind == "updated":
            # start the new launcher and get out of its way
            subprocess.Popen(["open", "-n", str(self.bundle)])
            self.root.after(300, self.root.destroy)
        else:
            self.busy = None
            self.close_popup()
            self.error(f"Update failed: {msg}")
            self.refresh()

    # macos enhancements

    def macmods_on(self):
        return self.settings.get("macmods", True)

    def set_macmods(self, on):
        self.settings["macmods"] = on
        save_settings(self.settings)
        self.cv.itemconfig(self.macmods_mark, state="normal" if on else "hidden")

    # mods

    def mods_on(self):
        return self.settings.get("mods", False)

    def show_mods(self):
        state = "normal" if self.mods_on() else "hidden"
        self.cv.itemconfig(self.mods_mark, state=state)
        self.cv.itemconfig(self.plugins_link, state=state)

    def toggle_mods(self):
        if self.busy:
            return
        self.settings["mods"] = not self.mods_on()
        save_settings(self.settings)
        self.show_mods()
        self.error("")
        if APP.exists() and modloader.enabled(APP) != self.mods_on():
            self.apply_mods()

    def apply_mods(self, then=None):
        # re signs the built app so it takes a few seconds
        self.busy = "mods"
        self.open_popup("Mods")
        self.popup.set(0.3)
        self.refresh()
        threading.Thread(target=self.mods_thread, args=(self.mods_on(), then), daemon=True).start()

    def mods_thread(self, on, then):
        try:
            modloader.set_mods(APP, on)
            self.q.put(("mods_done", then))
        except Exception as e:
            self.q.put(("mods_fail", (on, str(e))))

    def on_mods_msg(self, kind, msg):
        self.busy = None
        if kind == "mods_done":
            self.popup.set(1.0)
            self.root.after(300, self.close_popup)
            if msg:
                msg()
        else:
            on, err = msg
            self.close_popup()
            self.settings["mods"] = not on
            save_settings(self.settings)
            self.show_mods()
            self.error(f"Could not turn mods {'on' if on else 'off'}: {err}")
        self.refresh()

    def open_plugins(self):
        d = modloader.bepinex_dir()
        try:
            if not d.exists():
                modloader.install_loader()
        except Exception as e:
            self.error(f"Could not make the BepInEx folder: {e}")
            return
        subprocess.run(["open", str(d)])

    # get files

    def get_files(self):
        SteamNotice(self.root, self.open_steam)

    def open_steam(self):
        app, depot = EDITIONS[self.edition]
        cmd = f"download_depot {app} {depot}"
        self.root.clipboard_clear()
        self.root.clipboard_append(cmd)
        self.error("")
        self.watch_from = len(console_lines())
        self.busy = "download"
        self.open_popup("Game files")
        self.refresh()
        subprocess.run(["open", "steam://open/console"])

    def watch_download(self):
        depot = EDITIONS[self.edition][1]
        ev = depot_events(depot, self.watch_from)
        if ev.get("failed"):
            self.busy = None
            self.close_popup()
            self.chain = False
            self.error("Steam is offline. Close Steam on any other computer signed in "
                       "to this account, then try again." if ev["failed"] == "offline"
                       else f"Steam could not download the files: {ev['failed']}")
            self.refresh()
        elif ev.get("done"):
            self.popup.set(1.0)
            self.busy = None
            self.root.after(400, self.close_popup)
            self.depot_manifest()  # records it before steams log rotates
            self.refresh()
            if self.chain:
                self.root.after(600, self.resume_update)
        elif ev.get("files"):
            d = depot_dir(self.edition)
            have = sum(1 for p in d.rglob("*") if p.is_file()) if d.exists() else 0
            self.popup.set(min(0.99, have / ev["files"]))

    # build

    def start_build(self):
        self.error("")
        self.busy = "build"
        self.open_popup("Native app")
        self.creep_to = 0.0
        self.refresh()
        # the manifest on disk since steams public one can be newer
        ed, manifest = self.edition, self.depot_manifest()
        threading.Thread(target=self.build_thread, args=(ed, manifest), daemon=True).start()

    def build_thread(self, ed, manifest):
        appid = EDITIONS[ed][0]
        new = APP.with_name("Casualties Unknown.new.app")
        try:
            APP.parent.mkdir(parents=True, exist_ok=True)
            cubuild.build(depot_dir(ed), new, appid, manifest,
                          log=lambda m: self.q.put(("log", m)), mods=self.mods_on())
            if APP.exists():  # old build goes to the trash and never gets straight up deleted
                trash = pathlib.Path.home() / ".Trash" / f"Casualties Unknown {time.strftime('%H%M%S')}.app"
                shutil.move(str(APP), str(trash))
            new.rename(APP)
            self.q.put(("done", None))
        except Exception as e:  # just show it to the player cause theres nothing else we can do
            self.q.put(("fail", str(e)))

    def on_build_msg(self, kind, msg):
        if kind == "log":
            if msg in STEPS:
                v = STEPS[msg]
                self.popup.set(v)
                later = sorted(x for x in STEPS.values() if x > v)
                self.creep_to = (later[0] if later else 1.0) - 0.01
        elif kind == "done":
            self.busy = None
            self.popup.set(1.0)
            self.root.after(400, self.close_popup)
            self.refresh()
            if self.chain:
                self.root.after(600, self.resume_update)
        else:
            self.chain = False
            self.busy = None
            self.close_popup()
            self.error(f"Build failed: {msg}")
            self.refresh()

    # play

    def play(self):
        # an app built before the box existed, or flipped while it failed
        if modloader.enabled(APP) != self.mods_on():
            self.apply_mods(then=self.launch)
            return
        self.launch()

    def launch(self):
        if subprocess.run(["open", str(APP)]).returncode:
            self.error("The game would not start.")

    # loop

    def slide_dune(self, f):
        # Slides in from past the bottom left corner and chills there.
        t = min(1.0, f / 18)
        ease = 1 - (1 - t) ** 3
        x = -120 + 96 * ease
        self.cv.coords(self.dune_id, x, H + 6)
        if t < 1:
            self.root.after(16, self.slide_dune, f + 1)

    def tick(self):
        while not self.q.empty():
            kind, msg = self.q.get()
            if kind in ("update", "uprog", "updated", "upfail"):
                self.on_update_msg(kind, msg)
            elif kind in ("mods_done", "mods_fail"):
                self.on_mods_msg(kind, msg)
            else:
                self.on_build_msg(kind, msg)
        if self.busy == "build" and self.popup and self.popup.value < self.creep_to:
            self.popup.set(self.popup.value + (self.creep_to - self.popup.value) * 0.02)
        if self.busy == "download":
            self.watch_download()
            self.root.after(500, self.tick)
            return
        self.root.after(100 if self.busy else 1500, self.tick_idle if not self.busy else self.tick)

    def tick_idle(self):
        self.refresh()
        self.tick()


def main():
    root = tk.Tk()
    make_fonts()
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
