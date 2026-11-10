#!/usr/bin/env python3 -I
"""
when the dune lowky such a cutie you lowky jus pet
"""

import json, os, pathlib, queue, re, shutil, subprocess, sys, threading, time
import tkinter as tk
import tkinter.font as tkfont

HERE = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE))
from cupatch import build as cubuild  # noqa: E402

ASSETS = HERE / "assets"
STEAM = pathlib.Path.home() / "Library/Application Support/Steam"
CONTENT = STEAM / "Steam.AppBundle/Steam/Contents/MacOS/steamapps/content"
CONSOLE_LOG = STEAM / "logs/console_log.txt"
APP = pathlib.Path(os.environ.get("CUPORT_APP", pathlib.Path.home() / "Applications/Casualties Unknown.app"))
EDITIONS = {"full": (cubuild.FULL, 4576491), "demo": (cubuild.DEMO, 4576511)}

W, H = 440, 268
INK, FILL, DIM = "#000000", "#0000cc", "#a0a0a0"

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
    # last download state for a depot in steam's console log, starting at line `since`
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


FONT = SMALL = BIG = ITALIC = None


def make_fonts():
    global FONT, SMALL, BIG, ITALIC
    base = tkfont.nametofont("TkDefaultFont")
    SMALL = base.copy()
    FONT = base.copy()
    FONT.configure(weight="bold")
    ITALIC = base.copy()
    ITALIC.configure(slant="italic")
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
    # pops up over the launcher while something runs, like windows does
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
        # last line is three pieces so "own" can be italic
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
        # edition label and both radios, centered as one row
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

        bw, gap = 84, 8
        bx = mid - (3 * bw + 2 * gap) / 2
        self.b_files = Button(cv, bx, 208, bw, "Get files", self.get_files)
        self.b_build = Button(cv, bx + bw + gap, 208, bw, "Build", self.start_build)
        self.b_play = Button(cv, bx + 2 * (bw + gap), 208, bw, "Play", self.play)
        self.err = cv.create_text(mid, 252, text="", font=SMALL, fill="#ff0000",
                                  width=W - 40, justify="center")

        self.dune = tk.PhotoImage(file=str(ASSETS / "dune.png"))
        self.dune_id = cv.create_image(-120, H + 6, image=self.dune, anchor="sw")
        cv.tag_lower(self.dune_id)

        self.q = queue.Queue()
        self.busy = None  # "download" or "build" while one is going
        self.popup = None
        self.watch_from = 0
        self.creep_to = 0.0
        self.pick(self.edition)
        root.after(400, self.slide_dune, 0)
        root.after(200, self.tick)

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

    def latest_manifest(self):
        return depot_events(EDITIONS[self.edition][1]).get("manifest")

    def refresh(self):
        ready = self.depot_ready()
        info = built_info()
        appid = EDITIONS[self.edition][0]
        current = bool(info and info.get("appid") == appid and APP.exists()
                       and (info.get("manifest") == self.latest_manifest() or not self.latest_manifest()))
        idle = not self.busy
        self.b_files.set(idle)
        self.b_build.set(idle and ready and not current)
        self.b_play.set(idle and APP.exists())

    def open_popup(self, title):
        self.popup = ProgressWindow(self.root, title)

    def close_popup(self):
        if self.popup:
            self.popup.close()
            self.popup = None

    def error(self, msg):
        self.cv.itemconfig(self.err, text=msg)

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
            self.error("Steam is offline. Close Steam on any other computer signed in "
                       "to this account, then try again." if ev["failed"] == "offline"
                       else f"Steam could not download the files: {ev['failed']}")
            self.refresh()
        elif ev.get("done"):
            self.popup.set(1.0)
            self.busy = None
            self.root.after(400, self.close_popup)
            self.refresh()
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
        ed, manifest = self.edition, self.latest_manifest()
        threading.Thread(target=self.build_thread, args=(ed, manifest), daemon=True).start()

    def build_thread(self, ed, manifest):
        appid = EDITIONS[ed][0]
        new = APP.with_name("Casualties Unknown.new.app")
        try:
            APP.parent.mkdir(parents=True, exist_ok=True)
            cubuild.build(depot_dir(ed), new, appid, manifest,
                          log=lambda m: self.q.put(("log", m)))
            if APP.exists():  # old build goes to the trash, never straight up deleted
                trash = pathlib.Path.home() / ".Trash" / f"Casualties Unknown {time.strftime('%H%M%S')}.app"
                shutil.move(str(APP), str(trash))
            new.rename(APP)
            self.q.put(("done", None))
        except Exception as e:  # just show it to the player, nothing else we can do
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
        else:
            self.busy = None
            self.close_popup()
            self.error(f"Build failed: {msg}")
            self.refresh()

    # play

    def play(self):
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
            self.on_build_msg(*self.q.get())
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
