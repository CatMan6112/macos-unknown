"""packs the prebuilt stuff the patcher needs into patcher/payload

usage: .venv/bin/python -I patcher/make_payload.py

reads build/Shell.app and build/ShaderShell.app and build/SteamLib.app (from
the scripts in scripts/). the empty mac unity player goes to payload/Shell.app
and every metal Shader from the donor goes to shaders.json.gz. the mac
steamworks dll and steam_api.bundle go to steam/ and the icon to PlayerIcon.icns.
build/modloader (libdoorstop.dylib + BepInEx/core, the arm64 capable rebuilds)
goes to mods/. the engine version it was built for goes in payload.json
"""
import gzip, json, pathlib, shutil, subprocess, sys
import UnityPy

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "build"
OUT = ROOT / "patcher" / "payload"
UNITY = "2022.3.62f3"

sys.path.insert(0, str(ROOT / "patcher"))
from cupatch.tt import encode

if OUT.exists():
    sys.exit(f"{OUT} already exists; move it aside first")
OUT.mkdir()

subprocess.run(["ditto", str(B / "Shell.app"), str(OUT / "Shell.app")], check=True)

shaders = {}
env = UnityPy.load(str(B / "ShaderShell.app/Contents/Resources/Data"))
for obj in env.objects:
    if obj.type.name == "Shader":
        tt = obj.read_typetree()
        name = tt["m_ParsedForm"]["m_Name"]
        if 14 in tt["platforms"]:
            shaders.setdefault(name, tt)
with gzip.open(OUT / "shaders.json.gz", "wt") as f:
    json.dump(encode(shaders), f)
print(f"shaders: {len(shaders)}")

S = B / "SteamLib.app/Contents"
(OUT / "steam").mkdir()
shutil.copy2(S / "Resources/Data/Managed/com.rlabrecque.steamworks.net.dll", OUT / "steam")
subprocess.run(["ditto", str(S / "PlugIns/steam_api.bundle"), str(OUT / "steam/steam_api.bundle")], check=True)

subprocess.run(["ditto", str(B / "modloader"), str(OUT / "mods")], check=True)

icns = ROOT / "patcher/assets/cu-apple.icns"
shutil.copy2(icns, OUT / "PlayerIcon.icns")

(OUT / "payload.json").write_text(json.dumps({"unity": UNITY, "shaders": len(shaders)}, indent=1))
print(f"wrote {OUT}")
