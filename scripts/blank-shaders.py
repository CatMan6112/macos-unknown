"""swaps named shader graphs in a built app for CU/Invisible, for testing

usage: python -I blank-shaders.py <app> Graph1 Graph2 ...
edits <app> in place so only run it on a throwaway copy
"""
import gzip, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "patcher"))
import UnityPy
from cupatch.tt import decode

app = pathlib.Path(sys.argv[1]); names = set(sys.argv[2:])
donor = decode(json.load(gzip.open(pathlib.Path(__file__).resolve().parent.parent / "patcher/payload/shaders.json.gz", "rt")))
inv = donor["CU/Invisible"]
D = app / "Contents/Resources/Data"
env = UnityPy.load(str(D))
changed = set()
for o in env.objects:
    if o.type.name != "Shader" or o.assets_file.name in ("unity default resources", "unity_builtin_extra"):
        continue
    tt = o.read_typetree(); n = tt["m_ParsedForm"]["m_Name"]
    if n.startswith("Shader Graphs/") and n[14:] in names:
        new = dict(inv); new["m_ParsedForm"] = dict(inv["m_ParsedForm"], m_Name=n)
        new["m_Dependencies"] = []
        for k in ("m_NonModifiableTextures",):
            if k in tt: new[k] = tt[k]
        o.save_typetree(new); changed.add(o.assets_file); print("blanked", n)
for af in changed:
    (D / af.name).write_bytes(af.save())
