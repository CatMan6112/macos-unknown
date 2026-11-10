"""props of named shader graphs (D3D11 originals in CU.app) plus every material
using them with its saved values"""
import sys, UnityPy
want = set(sys.argv[2:])
env = UnityPy.load(sys.argv[1])
ids = {}
for obj in env.objects:
    if obj.type.name == "Shader":
        tt = obj.read_typetree(); n = tt["m_ParsedForm"]["m_Name"][14:]
        if n in want:
            ids[(obj.assets_file.name, obj.path_id)] = n
            print("==", n)
            for p in tt["m_ParsedForm"]["m_PropInfo"]["m_Props"]:
                print("  ", p["m_Name"], p["m_Description"], "type", p["m_Type"], p["m_DefValue[0]"], p["m_DefValue[1]"], p["m_DefValue[2]"], p["m_DefValue[3]"], p.get("m_DefTexture", {}).get("m_DefaultName", ""))
for obj in env.objects:
    if obj.type.name == "Material":
        m = obj.read()
        try:
            sh = m.m_Shader.deref(); key = (sh.assets_file.name, sh.path_id)
        except Exception:
            continue
        if key in ids:
            tt = obj.read_typetree(); sp = tt["m_SavedProperties"]
            print("-- material", tt["m_Name"], "->", ids[key], "keywords", tt.get("m_ValidKeywords"))
            for k, v in sp["m_Colors"]: print("     color", k, v)
            for k, v in sp["m_Floats"]: print("     float", k, v)
            for k, v in sp["m_TexEnvs"]:
                t = v["m_Texture"]
                name = ""
                if t["m_PathID"]:
                    try: name = obj.assets_file.objects[t["m_PathID"]].read().m_Name if t["m_FileID"] == 0 else f"ext{t['m_FileID']}:{t['m_PathID']}"
                    except Exception as e: name = f"? {e}"
                print("     tex", k, name, v["m_Scale"], v["m_Offset"])
