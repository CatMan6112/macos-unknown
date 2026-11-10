"""copies metal shaders from a donor player's data into a copy of the game data

usage: python -I swap-shaders.py <donor Data> <game Data to patch in place>

matches Shader objects by name and swaps in the donor's compiled code. the game
keeps its own dependency and texture pointers cause the donor's point into the
donor's files
"""
import sys, pathlib, UnityPy

donor_dir, game_dir = map(pathlib.Path, sys.argv[1:3])
KEEP = ("m_Dependencies", "m_NonModifiableTextures")

# shader graphs got no metal build so each gets a donor shader under its own name
# CUG/<graph> comes out of dx2hlsl.py (shell/Assets/Shaders/Generated)
GRAPHS = """AberrationShader AlgaeShader BlueHeartPulseShader BonusPass CrystalShimmer DamageScreen
DirtWaterShader DuneShader Emissivesprite FogShader HoverShader HumanShader Limb LiquidFill MagmaShader
ObserverShader OilShader ProgressiveDestructShader RadBackground RadLine RainShader RedSludgeShader
SapShader ScreenPass ScreenSpaceDistortion Snowfall WallHole WaterShader""".split()
ALIAS = {g: "CUG/" + g for g in GRAPHS}
# old hand ports still around as a fallback (CU/Water DirtWater Oil Sap Dune and
# Algae in shell/Assets/Shaders). to use one add it to ALIAS under the graph name

donor = {}
denv = UnityPy.load(str(donor_dir))
for obj in denv.objects:
    if obj.type.name == "Shader":
        tt = obj.read_typetree()
        name = tt["m_ParsedForm"]["m_Name"]
        if 14 in tt["platforms"]:
            donor.setdefault(name, tt)
print(f"donor shaders: {len(donor)}")

genv = UnityPy.load(str(game_dir))
changed = set()
missing = []
for obj in genv.objects:
    if obj.type.name != "Shader":
        continue
    f = obj.assets_file.name
    if f in ("unity default resources", "unity_builtin_extra"):
        continue
    tt = obj.read_typetree()
    name = tt["m_ParsedForm"]["m_Name"]
    src = name
    if name.startswith("Shader Graphs/") and name[14:] in ALIAS:
        src = ALIAS[name[14:]]
    if src not in donor:
        missing.append(name)
        continue
    new = dict(donor[src])
    for k in KEEP:
        if k in tt:
            new[k] = tt[k]
    if src != name:
        # keep the graph's name or Shader.Find and material lookups break
        new["m_ParsedForm"] = dict(new["m_ParsedForm"], m_Name=name)
        new["m_Dependencies"] = []
    obj.save_typetree(new)
    changed.add(obj.assets_file)
    print(f"swapped {f}:{obj.path_id} {name}" + (f" <- {src}" if src != name else ""))

# game only lists D3D11 (2). the player wont touch metal (16) unless its listed
# so you just get a null device and shit
for obj in genv.objects:
    if obj.type.name == "BuildSettings":
        tt = obj.read_typetree()
        print("graphics APIs", tt["m_GraphicsAPIs"], "-> [16]")
        tt["m_GraphicsAPIs"] = [16]
        obj.save_typetree(tt)
        changed.add(obj.assets_file)

for af in changed:
    out = game_dir / af.name
    data = af.save()
    out.write_bytes(data)
    print(f"wrote {out.name} ({len(data)} bytes)")
print("not swapped:", *sorted(set(missing)), sep="\n  ")
