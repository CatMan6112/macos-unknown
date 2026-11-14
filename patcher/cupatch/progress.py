r"""turns mac progress into a .reg file the windows game can load

unlocks and the casualty count and the deepest layer arent in save.sv. theyre PlayerPrefs
so on mac thats the com.Orsoniks.CasualtiesUnknown defaults domain and on windows its
HKCU\Software\Orsoniks\CasualtiesUnknown in the registry. the game sets wonchar<char> to 1
when a run is won and character N shows up once wonchar<N-1> is set

unity tacks _h<hash> onto every registry name on windows. the hash is djb2 with xor and
it matches what the windows game writes
"""
import plistlib, re, subprocess

DOMAIN = "com.Orsoniks.CasualtiesUnknown"
KEY = r"HKEY_CURRENT_USER\Software\Orsoniks\CasualtiesUnknown"
# only progress goes over. screen size and mod settings and the session id stay on each machine
# the did* ones are the endings and come back with achievements anyway but its cheap to bring them
KEEP = re.compile(r"wonchar\d+|deathcount|deepestlayer|did(basiccourse|biopod|escape|merc)|tut(orial|complete)")


def prefs():
    # defaults export goes through cfprefsd so it sees what the game wrote even if the plist on disk is behind
    out = subprocess.run(["defaults", "export", DOMAIN, "-"], capture_output=True)
    if out.returncode:
        return {}
    return plistlib.loads(out.stdout)


def progress(d=None):
    d = prefs() if d is None else d
    # bool is an int in python but plists keep them apart and the game only writes ints
    return {k: v for k, v in sorted(d.items())
            if KEEP.fullmatch(k) and isinstance(v, int) and not isinstance(v, bool)}


def reg_name(key):
    h = 5381
    for c in key.encode():
        h = ((h * 33) ^ c) & 0xFFFFFFFF
    return f"{key}_h{h}"


def to_reg(p):
    lines = ["Windows Registry Editor Version 5.00", "", f"[{KEY}]"]
    lines += [f'"{reg_name(k)}"=dword:{v & 0xFFFFFFFF:08x}' for k, v in p.items()]
    # regedit wants utf-16 with a bom and crlf for the 5.00 header
    return ("\r\n".join(lines) + "\r\n").encode("utf-16")


def export(path):
    """writes the .reg and hands back what went in it. empty means theres nothing to move yet"""
    p = progress()
    if p:
        with open(path, "wb") as f:
            f.write(to_reg(p))
    return p
