r"""moves saves out of the backslash files and into the real save folder

the game builds its paths with a backslash before save.sv and console.json. windows
reads that as a folder and mac doesnt, so the native game wrote a file called
CasualtiesUnknown\save.sv next to the CasualtiesUnknown folder. a save copied over
from windows goes in the folder and the game never saw it

MONO_IOMAP=all in Info.plist makes mono treat the backslash like a slash so the game
uses the folder like it does on windows. this moves the old files in before the game
starts. if theres already a file in the folder the newer one wins and the other one
goes to backups. nothing gets deleted
"""
import pathlib, plistlib, shutil, time

SUPPORT = pathlib.Path.home() / "Library/Application Support"
BACKUPS = SUPPORT / "macos-unknown/save-backups"
NAMES = ("save.sv", "console.json")
# unity uses Orsoniks/CasualtiesUnknown and older shells used the bundle id
DATA = (SUPPORT / "Orsoniks/CasualtiesUnknown", SUPPORT / "com.Orsoniks.CasualtiesUnknown")


def stray():
    """every old backslash file still lying around and where it goes"""
    out = []
    for d in DATA:
        for n in NAMES:
            old = d.parent / f"{d.name}\\{n}"
            if old.is_file():
                out.append((old, d / n))
    return out


def backup(p):
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = p.name.rsplit("\\", 1)[-1]
    dst, i = BACKUPS / f"{stamp}-{name}", 1
    while dst.exists():
        dst, i = BACKUPS / f"{stamp}-{i}-{name}", i + 1
    shutil.move(str(p), str(dst))
    return dst


def migrate(log=print):
    for old, new in stray():
        new.parent.mkdir(parents=True, exist_ok=True)
        if new.exists():
            # theres a save in the folder already so keep the newer one and back up the other
            if old.stat().st_mtime > new.stat().st_mtime:
                log(f"backed up the older {new} to {backup(new)}")
            else:
                log(f"backed up the older {old} to {backup(old)}")
                continue
        shutil.move(str(old), str(new))
        log(f"moved {old} to {new}")


def fixed(app):
    """True if the app reads saves from the folder. apps from before this dont"""
    try:
        p = plistlib.loads((pathlib.Path(app) / "Contents/Info.plist").read_bytes())
    except (OSError, ValueError):
        return False
    return p.get("LSEnvironment", {}).get("MONO_IOMAP") == "all"
