"""turns mod loaders on or off for a built app

off: the app gets signed with the hardened runtime and no dyld entitlement, so
dyld throws away DYLD_INSERT_LIBRARIES and doorstop (or anything else) never
gets in. CUPort.dll also quits the game if it finds a loader anyway

on: BepInEx and libdoorstop go to ~/Library/Application Support/macos-unknown/mods
so plugins survive rebuilds, Info.plist points doorstop at them, and the
signature gets the entitlement that lets dyld take the env vars

the jit, unsigned memory and library validation entitlements are there in both
cases. mono needs the first two and steamclient.dylib is signed by valve so the
third one is what lets it load
"""
import json, os, pathlib, plistlib, shutil, subprocess, tempfile

PAYLOAD = pathlib.Path(__file__).resolve().parent.parent / "payload"
MODS = pathlib.Path.home() / "Library/Application Support/macos-unknown/mods"
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
              "LaunchServices.framework/Support/lsregister")
BASE = {"com.apple.security.cs.allow-jit": True,
        "com.apple.security.cs.allow-unsigned-executable-memory": True,
        "com.apple.security.cs.disable-library-validation": True}
DYLD = "com.apple.security.cs.allow-dyld-environment-variables"
ENV = ("DOORSTOP_ENABLED", "DOORSTOP_TARGET_ASSEMBLY", "DYLD_INSERT_LIBRARIES")


def available():
    return (PAYLOAD / "mods/libdoorstop.dylib").is_file()


def plugins_dir():
    return MODS / "BepInEx/plugins"


def install_loader():
    # core gets replaced every time so a launcher update brings the new one.
    # plugins, config and patchers belong to the player and never get touched
    src = PAYLOAD / "mods"
    core = MODS / "BepInEx/core"
    if core.exists():
        shutil.rmtree(core)
    core.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ditto", str(src / "BepInEx/core"), str(core)], check=True, capture_output=True)
    shutil.copy2(src / "libdoorstop.dylib", MODS / "libdoorstop.dylib")
    # the licenses go wherever the dlls go
    subprocess.run(["ditto", str(src / "licenses"), str(MODS / "licenses")], check=True, capture_output=True)
    for d in ("plugins", "patchers", "config"):
        (MODS / "BepInEx" / d).mkdir(exist_ok=True)


def sign(app, on):
    ents = dict(BASE, **({DYLD: True} if on else {}))
    with tempfile.NamedTemporaryFile(suffix=".plist", delete=False) as f:
        f.write(plistlib.dumps(ents))
    try:
        subprocess.run(["codesign", "--force", "--deep", "-s", "-", "-o", "runtime",
                        "--entitlements", f.name, str(app)], check=True, capture_output=True)
    finally:
        os.unlink(f.name)


def configure(app, on):
    """writes Info.plist and cuport.json for on or off. doesnt sign"""
    app = pathlib.Path(app)
    if on:
        install_loader()
    info = app / "Contents/Info.plist"
    p = plistlib.loads(info.read_bytes())
    env = {k: v for k, v in p.get("LSEnvironment", {}).items() if k not in ENV}
    if on:
        env.update(DOORSTOP_ENABLED="1",
                   DOORSTOP_TARGET_ASSEMBLY=str(MODS / "BepInEx/core/BepInEx.Preloader.dll"),
                   DYLD_INSERT_LIBRARIES=str(MODS / "libdoorstop.dylib"))
    p["LSEnvironment"] = env
    info.write_bytes(plistlib.dumps(p))
    meta = app / "Contents/Resources/cuport.json"
    try:
        d = json.loads(meta.read_text())
    except (OSError, ValueError):
        d = {}
    d["mods"] = bool(on)
    meta.write_text(json.dumps(d, indent=1))


def enabled(app):
    """True or False, None for apps built before the box existed (no block on those yet)"""
    try:
        return json.loads((pathlib.Path(app) / "Contents/Resources/cuport.json").read_text()).get("mods")
    except (OSError, ValueError):
        return None


def set_mods(app, on):
    """flips a built app. launch services caches LSEnvironment so it gets told to reread it"""
    if on and not available():
        raise RuntimeError("this launcher has no mod loader in it")
    configure(app, on)
    sign(app, on)
    subprocess.run([LSREGISTER, "-f", str(app)], capture_output=True)
