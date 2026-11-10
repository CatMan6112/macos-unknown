"""prints BuildSettings and the graphics PlayerSettings fields of a Data folder"""
import sys, UnityPy
env = UnityPy.load(sys.argv[1] + "/globalgamemanagers")
for obj in env.objects:
    if obj.type.name in ("BuildSettings", "PlayerSettings"):
        tt = obj.read_typetree()
        for k, v in tt.items():
            s = repr(v)
            if obj.type.name == "BuildSettings" or any(w in k.lower() for w in ("graphic", "api", "metal", "gfx", "jobs", "colorspace")):
                print(obj.type.name, k, s[:300])
