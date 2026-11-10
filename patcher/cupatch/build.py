"""turns a windows Casualties: Unknown folder into a real mac app

usage: python -I -m cupatch.build <game folder> <output .app> [--appid N] [--manifest ID]

<game folder> is whatever has CasualtiesUnknown_Data in it, like what steam's
`download_depot 4576490 4576491` spits out. its read only. the app gets built
in a staging folder next to <output .app> and moved over at the end, so a
failed build doesnt leave half an app lying around
"""
import argparse, gzip, json, pathlib, plistlib, shutil, subprocess, sys, time
import UnityPy

from .tt import decode

PAYLOAD = pathlib.Path(__file__).resolve().parent.parent / "payload"
FULL, DEMO = 4576490, 4576510
KEEP = ("m_Dependencies", "m_NonModifiableTextures")
# shader graphs got no metal build so each one gets swapped for its CUG/ port
GRAPHS = """AberrationShader AlgaeShader BlueHeartPulseShader BonusPass CrystalShimmer DamageScreen
DirtWaterShader DuneShader Emissivesprite FogShader HoverShader HumanShader Limb LiquidFill MagmaShader
ObserverShader OilShader ProgressiveDestructShader RadBackground RadLine RainShader RedSludgeShader
SapShader ScreenPass ScreenSpaceDistortion Snowfall WallHole WaterShader""".split()


class BuildError(Exception):
    pass


def run(*cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def find_data(game):
    game = pathlib.Path(game)
    for d in [game, *game.iterdir()] if game.is_dir() else []:
        if d.name.endswith("_Data") and (d / "globalgamemanagers").is_file():
            return d
    raise BuildError(f"no CasualtiesUnknown_Data folder in {game}")


def check_version(data, want):
    env = UnityPy.load(str(data / "globalgamemanagers"))
    have = next(iter(env.files.values())).unity_version
    if have != want:
        raise BuildError(f"game uses Unity {have}, this patcher supports {want}")


def swap_shaders(data, log):
    with gzip.open(PAYLOAD / "shaders.json.gz", "rt") as f:
        donor = decode(json.load(f))
    env = UnityPy.load(str(data))
    changed, missing, n = set(), set(), 0
    for obj in env.objects:
        t = obj.type.name
        if t == "Shader":
            if obj.assets_file.name in ("unity default resources", "unity_builtin_extra"):
                continue
            tt = obj.read_typetree()
            name = tt["m_ParsedForm"]["m_Name"]
            src = name
            if name.startswith("Shader Graphs/") and name[14:] in GRAPHS:
                src = "CUG/" + name[14:]
            if src not in donor:
                missing.add(name)
                continue
            new = dict(donor[src])
            for k in KEEP:
                if k in tt:
                    new[k] = tt[k]
            if src != name:
                # keep the graph's own name so material lookups still match
                new["m_ParsedForm"] = dict(new["m_ParsedForm"], m_Name=name)
                new["m_Dependencies"] = []
            obj.save_typetree(new)
            changed.add(obj.assets_file)
            n += 1
        elif t == "BuildSettings":
            # game only lists D3D11 (2). without metal (16) you get a null device and a black fucking screen
            tt = obj.read_typetree()
            tt["m_GraphicsAPIs"] = [16]
            obj.save_typetree(tt)
            changed.add(obj.assets_file)
        elif t == "PlayerSettings":
            tt = obj.read_typetree()
            # retina off. menus pull 18.5 W of GPU at 3024x1898 vs 2 W at 1512x949
            # on an M5, performance is ass with it on. gameplay looks the same
            # either way, and sizes stay in points so they always fit the screen
            tt["macRetinaSupport"] = False
            tt["resizableWindow"] = True
            # off in the game, and on mac that breaks fullscreen -> windowed. unity
            # says Windowed but the NSWindow just stays fullscreen at the old size, which is some bullshit
            tt["allowFullscreenSwitch"] = True
            obj.save_typetree(tt)
            changed.add(obj.assets_file)
    for af in changed:
        (data / af.name).write_bytes(af.save())
    log(f"swapped {n} shaders, {len(missing)} without a Metal build")
    return sorted(missing)


def install_cuport(data):
    shutil.copy2(PAYLOAD / "CUPort.dll", data / "Managed/CUPort.dll")
    p = data / "ScriptingAssemblies.json"
    sa = json.loads(p.read_text())
    if "CUPort.dll" not in sa["names"]:
        sa["names"].append("CUPort.dll")
        sa["types"].append(16)  # user assembly, like Assembly-CSharp
        p.write_text(json.dumps(sa, separators=(",", ":")))
    p = data / "RuntimeInitializeOnLoads.json"
    ri = json.loads(p.read_text())
    entry = {"assemblyName": "CUPort", "nameSpace": "CUPort", "className": "Boot",
             "methodName": "Init", "loadTypes": 1, "isUnityClass": False}  # 1: before scene load
    if entry not in ri["root"]:
        ri["root"].append(entry)
        p.write_text(json.dumps(ri, separators=(",", ":")))


def build(game, out, appid=FULL, manifest=None, log=print):
    out = pathlib.Path(out)
    src = find_data(game)
    want = json.loads((PAYLOAD / "payload.json").read_text())["unity"]
    log("checking engine version")
    check_version(src, want)

    stage = out.with_name(out.stem + ".building.app")
    if stage.exists():
        raise BuildError(f"{stage} is left over from an earlier build; remove it first")
    try:
        log("copying the macOS player")
        run("ditto", str(PAYLOAD / "Shell.app"), str(stage))
        C = stage / "Contents"
        R = C / "Resources"
        shell = R / "Data"
        D = R / "Data.game"

        log("copying game data")
        run("ditto", str(src), str(D))
        shutil.rmtree(D / "Plugins", ignore_errors=True)  # windows only native plugins, useless here
        # same engine version so the mac builtin resources just drop in
        shutil.copy2(shell / "Resources/unity_builtin_extra", D / "Resources/unity_builtin_extra")
        shutil.copy2(R / "unity default resources", D / "Resources/unity default resources")
        # the game ships windows class libs that P/Invoke kernel32, swap in the mac ones
        for f in (shell / "Managed").glob("*.dll"):
            if f.name.startswith(("mscorlib", "System", "Mono", "netstandard")):
                shutil.copy2(f, D / "Managed" / f.name)
        shutil.rmtree(shell)
        D.rename(shell)
        D = shell

        log("swapping shaders for Metal")
        missing = swap_shaders(D, log)

        log("installing Steam for macOS")
        shutil.copy2(PAYLOAD / "steam/com.rlabrecque.steamworks.net.dll", D / "Managed")
        run("ditto", str(PAYLOAD / "steam/steam_api.bundle"), str(C / "PlugIns/steam_api.bundle"))

        log("installing the startup fix")
        install_cuport(D)

        # on mac Application.dataPath is Contents/ and not Contents/Resources/Data, idk why the fuck
        for name in ("Lang", "custommusic"):
            if (D / name).exists():
                (C / name).symlink_to(f"Resources/Data/{name}")
        shutil.copy2(PAYLOAD / "PlayerIcon.icns", R / "PlayerIcon.icns")

        info = C / "Info.plist"
        p = plistlib.loads(info.read_bytes())
        # finder launches start in / so steam_appid.txt never gets found and steam shits itself
        p["LSEnvironment"] = {"SteamAppId": str(appid), "SteamGameId": str(appid)}
        p["CFBundleName"] = p["CFBundleDisplayName"] = "Casualties Unknown"
        info.write_bytes(plistlib.dumps(p))
        (R / "cuport.json").write_text(json.dumps({
            "appid": appid, "manifest": manifest, "unity": want,
            "source": str(pathlib.Path(game).resolve()),
            "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "unswapped_shaders": missing,
        }, indent=1))

        log("signing")
        run("codesign", "--force", "--deep", "-s", "-", str(stage))
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    if out.exists():
        raise BuildError(f"{out} already exists; the new build is at {stage}")
    stage.rename(out)
    log(f"built {out}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("out")
    ap.add_argument("--appid", type=int, default=FULL)
    ap.add_argument("--manifest")
    a = ap.parse_args()
    try:
        build(a.game, a.out, a.appid, a.manifest)
    except BuildError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
