"""lists Shader objects in a Data folder with file, path_id, name and platforms"""
import sys, pathlib, UnityPy
d = pathlib.Path(sys.argv[1])
env = UnityPy.load(str(d))
for obj in env.objects:
    if obj.type.name != "Shader":
        continue
    try:
        tt = obj.read_typetree()
        name = tt["m_ParsedForm"]["m_Name"]
        plats = tt.get("platforms")
        nsub = len(tt["m_ParsedForm"]["m_SubShaders"])
    except Exception as e:
        name, plats, nsub = f"<err {e}>", None, -1
    print(f"{obj.assets_file.name}\t{obj.path_id}\t{name}\tplat={plats}\tsub={nsub}\tsize={obj.byte_size}")
