"""for each shader graph pass its name/LightMode/blend/zwrite/ztest/cull and the blob
index of each vertex/fragment variant with its keywords
usage: graph-state.py <Data> [name...]"""
import sys, UnityPy
env = UnityPy.load(sys.argv[1]); want = set(sys.argv[2:])
B = {0:"Zero",1:"One",2:"DstColor",3:"SrcColor",4:"OneMinusDstColor",5:"SrcAlpha",6:"OneMinusSrcColor",7:"DstAlpha",8:"OneMinusDstAlpha",9:"SrcAlphaSat",10:"OneMinusSrcAlpha"}
for o in env.objects:
    if o.type.name != "Shader": continue
    t = o.read_typetree(); pf = t["m_ParsedForm"]; n = pf["m_Name"]
    if not n.startswith("Shader Graphs/") or (want and n[14:] not in want): continue
    kw = pf.get("m_KeywordNames", [])
    print("==", n[14:], "target", pf["m_SubShaders"][0]["m_Passes"][0]["m_Tags"]["tags"])
    for p in pf["m_SubShaders"][0]["m_Passes"]:
        s = p["m_State"]; b = s["rtBlend0"]; tags = dict(s["m_Tags"]["tags"])
        bl = "%s %s, %s %s op%d" % tuple([B.get(int(b[k]["val"]), b[k]["val"]) for k in ("srcBlend","destBlend","srcBlendAlpha","destBlendAlpha")] + [int(b["blendOp"]["val"])])
        print(f"  pass {s['m_Name']!r} {tags.get('LIGHTMODE','')} blend[{bl}] zw{int(s['zWrite']['val'])} zt{int(s['zTest']['val'])} cull{int(s['culling']['val'])}")
        names = {v: k for k, v in p["m_NameIndices"]}
        fp = p["progFragment"]
        nvar = sum(len(x) for x in fp["m_PlayerSubPrograms"])
        cp = fp["m_CommonParameters"]
        print(f"    fragment variants {nvar}; textures " + ", ".join(f"t{t['m_Index']}={names.get(t['m_NameIndex'])}" for t in cp["m_TextureParams"]))
        for cb in cp["m_ConstantBuffers"]:
            vs = ", ".join(f"[{v['m_Index']//16}].{'xyzw'[(v['m_Index']%16)//4]}={names.get(v['m_NameIndex'])}" for v in cb["m_VectorParams"] + cb["m_MatrixParams"])
            print(f"    cb {names.get(cb['m_NameIndex'])}: {vs}")
        for sub in fp["m_PlayerSubPrograms"]:
            for sp in sub:
                ks = [kw[i] for i in sp.get("m_KeywordIndices", []) if i < len(kw)]
                if ks: print(f"      variant blob{sp['m_BlobIndex']}: {' '.join(ks)}")
