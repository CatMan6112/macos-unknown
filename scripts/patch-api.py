"""sets BuildSettings.m_GraphicsAPIs to metal in a Data folder's globalgamemanagers"""
import sys, pathlib, UnityPy
d = pathlib.Path(sys.argv[1])
env = UnityPy.load(str(d / "globalgamemanagers"))
for obj in env.objects:
    if obj.type.name == "BuildSettings":
        tt = obj.read_typetree(); print(tt["m_GraphicsAPIs"], "-> [16]")
        tt["m_GraphicsAPIs"] = [16]; obj.save_typetree(tt)
        (d / "globalgamemanagers").write_bytes(obj.assets_file.save())
