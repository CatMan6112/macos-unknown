"""pass names, tags and texture props for every shader graph"""
import sys, UnityPy
env = UnityPy.load(sys.argv[1])
for obj in env.objects:
    if obj.type.name != "Shader": continue
    tt = obj.read_typetree(); pf = tt["m_ParsedForm"]
    if not pf["m_Name"].startswith("Shader Graphs/"): continue
    sub = pf["m_SubShaders"][0]
    passes = [p["m_Name"] for p in sub["m_Passes"]]
    tags = {k: v for k, v in sub["m_Tags"]["tags"]}
    props = [p["m_Name"] for p in pf["m_PropInfo"]["m_Props"] if p["m_Type"] == 4]
    print(f"{pf['m_Name'][14:]:28} {tags.get('RenderType','')}/{tags.get('Queue','')} passes={passes} tex={props}")
