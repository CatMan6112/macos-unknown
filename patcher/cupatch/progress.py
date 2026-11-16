r"""moves progress between the mac port and the windows game

unlocks and the casualty count and the deepest layer arent in save.sv. theyre PlayerPrefs
so on mac thats the com.Orsoniks.CasualtiesUnknown defaults domain and on windows its
HKCU\Software\Orsoniks\CasualtiesUnknown in the registry. the game sets wonchar<char> to 1
when a run is won and character N shows up once wonchar<N-1> is set

unity tacks _h<hash> onto every registry name on windows. the hash is djb2 with xor and
it matches what the windows game writes

both ways keep the bigger number for each key. a .reg on its own would just overwrite, so
an older mac could drop deepestlayer on windows and lock layers again. thats why export
ships a .bat that reads the .reg and only raises values
"""
import pathlib, plistlib, re, shutil, subprocess, zipfile

from . import saves

DOMAIN = "com.Orsoniks.CasualtiesUnknown"
KEY = r"HKEY_CURRENT_USER\Software\Orsoniks\CasualtiesUnknown"
# only progress goes over. screen size and mod settings and the session id stay on each machine
# the did* ones are the endings and come back with achievements anyway but its cheap to bring them
KEEP = re.compile(r"wonchar\d+|deathcount|deepestlayer|did(basiccourse|biopod|escape|merc)|tut(orial|complete)")
REG_FILE = "CU progress.reg"
MAX_REG = 1 << 20

EXPORT_README = (
    "Before you ask, no, the script isnt malicious, you can read it if you'd like. The script "
    "automatically contains the code needed to apply the progress contained in the .reg file "
    "directly into your windows registry which the game reads from. If windows throws up any "
    "issues, try disabling your anti-virus or allowing it to run (I SWEAR ITS NOT A TROJAN "
    "PLEASE READ IT YOUVE GOTTA BELIEVE ME YOUVE GOTTANRRUHRIUGRHRGI) Enjoy :3\n")

IMPORT_README = (
    "Heyyyy!!! run the .bat file which will pull your game's files and compile it back into a "
    ".zip you can give to MOS:U, if you encounter any errors while trying to run the .bat, try "
    "disabling your anti virus or something (no its not a virus :<)\n")

# reads the .reg next to it and only raises values, so nothing on windows goes backwards.
# set /a takes the 0x hex straight from the dword. the old values get backed up first
APPLY_BAT = r"""@echo off
setlocal
set "KEY=HKCU\Software\Orsoniks\CasualtiesUnknown"
set "REG=%~dp0CU progress.reg"
if not exist "%REG%" (
  echo Cant find "CU progress.reg" next to this file. Unzip the whole folder first.
  pause
  exit /b 1
)
tasklist /fi "imagename eq CasualtiesUnknown.exe" | find /i "CasualtiesUnknown.exe" >nul && (
  echo Close Casualties Unknown first, then run this again.
  pause
  exit /b 1
)
reg query "%KEY%" >nul 2>&1 && reg export "%KEY%" "%~dp0backup before import.reg" /y >nul
for /f "usebackq tokens=1,2 delims==" %%a in (`type "%REG%" ^| find "=dword:"`) do call :put "%%~a" "%%b"
echo Done! Your progress is in. Go play :3
pause
exit /b 0

:put
set "NAME=%~1"
set "HEX=%~2"
set /a NEW=0x%HEX:dword:=%
set CUR=
for /f "tokens=3" %%v in ('reg query "%KEY%" /v "%NAME%" 2^>nul ^| find "REG_DWORD"') do set /a CUR=%%v
if defined CUR if %CUR% GEQ %NEW% exit /b 0
reg add "%KEY%" /v "%NAME%" /t REG_DWORD /d %NEW% /f >nul
exit /b 0
"""

# reg export writes the whole key, the mac side only takes the progress keys out of it.
# the zip goes on the desktop cause %~dp0 is a temp folder when its run from inside the zip
GET_BAT = r"""@echo off
setlocal
set "KEY=HKCU\Software\Orsoniks\CasualtiesUnknown"
tasklist /fi "imagename eq CasualtiesUnknown.exe" | find /i "CasualtiesUnknown.exe" >nul && (
  echo Close Casualties Unknown first, then run this again.
  pause
  exit /b 1
)
reg query "%KEY%" >nul 2>&1 || (
  echo Theres no Casualties Unknown progress on this PC yet.
  pause
  exit /b 1
)
set "TMPDIR=%TEMP%\mosu-progress"
if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%"
mkdir "%TMPDIR%"
reg export "%KEY%" "%TMPDIR%\CU progress.reg" /y >nul || (
  echo Couldnt read your progress from the registry.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $z = Join-Path ([Environment]::GetFolderPath('Desktop')) 'CU windows progress.zip'; Compress-Archive -LiteralPath (Join-Path $env:TMPDIR 'CU progress.reg') -DestinationPath $z -Force" || (
  echo Couldnt make the zip.
  pause
  exit /b 1
)
rmdir /s /q "%TMPDIR%"
echo Done! "CU windows progress.zip" is on your Desktop. Bring it back to your Mac :3
pause
"""


def prefs(domain=DOMAIN):
    # defaults export goes through cfprefsd so it sees what the game wrote even if the plist on disk is behind
    out = subprocess.run(["defaults", "export", domain, "-"], capture_output=True)
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


def crlf(s):
    return s.replace("\r\n", "\n").replace("\n", "\r\n").encode()


def export_zip(path):
    """writes the zip for windows and hands back what went in it. empty means theres nothing to move yet"""
    p = progress()
    if p:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(REG_FILE, to_reg(p))
            z.writestr("apply progress.bat", crlf(APPLY_BAT))
            z.writestr("readme.txt", crlf(EXPORT_README))
    return p


def helper_zip(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("get progress.bat", crlf(GET_BAT))
        z.writestr("readme.txt", crlf(IMPORT_README))


def decode_reg(raw):
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig", errors="replace")


def section(line):
    # regedit writes [HKEY_CURRENT_USER\Software\...]. wines user.reg leaves the hive off,
    # doubles the backslashes and puts a timestamp after the bracket
    name = line[1:line.find("]")].replace("\\\\", "\\").lower()
    return name in (KEY.lower(), KEY.split("\\", 1)[1].lower())


def parse_reg(text):
    """progress keys out of a .reg or a wine user.reg, with the _h hash taken back off"""
    out, inside = {}, False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            inside = section(line)
            continue
        m = inside and re.fullmatch(r'"(.+)_h(\d+)"=dword:([0-9a-fA-F]{1,8})', line)
        if not m:
            continue
        name, v = m.group(1), int(m.group(3), 16)
        # only trust names whose hash checks out so a mangled line cant sneak in
        if KEEP.fullmatch(name) and reg_name(name) == f"{name}_h{m.group(2)}":
            out[name] = v - (1 << 32) if v >= 1 << 31 else v
    return out


def read_zip(path):
    """progress from a zip the windows .bat made. raises ValueError if theres no .reg in it"""
    found = {}
    with zipfile.ZipFile(path) as z:
        regs = [i for i in z.infolist() if i.filename.lower().endswith(".reg")
                and "backup" not in i.filename.lower() and i.file_size <= MAX_REG]
        if not regs:
            raise ValueError("no .reg")
        for i in regs:
            for k, v in parse_reg(decode_reg(z.read(i))).items():
                found[k] = max(v, found.get(k, v))
    return found


def merge(have, incoming):
    """what to write so every key ends up at the bigger of the two"""
    return {k: v for k, v in sorted(incoming.items()) if v > have.get(k, 0)}


def import_zip(path, domain=DOMAIN):
    """writes the windows progress into mac prefs. hands back what was in the zip and what changed"""
    found = read_zip(path)
    todo = merge(progress(prefs(domain)), found)
    for k, v in todo.items():
        # through defaults so cfprefsd knows. editing the plist by hand gets overwritten from its cache
        subprocess.run(["defaults", "write", domain, k, "-int", str(v)], check=True)
    return found, todo


def game_running(app):
    exe = app / "Contents/MacOS/CasualtiesUnknown"
    return subprocess.run(["pgrep", "-f", str(exe)], capture_output=True).returncode == 0


# wine bottles that might have the windows game in them. the last two are
# sikarugir, kegworks and wineskin wrappers, which keep the prefix inside the .app
HOME = pathlib.Path.home()
BOTTLES = [
    (HOME / "Library/Application Support/CrossOver/Bottles", "*/user.reg"),
    (HOME / "Library/Containers/com.isaacmarovitz.Whisky/Bottles", "*/user.reg"),
    (HOME / "Applications", "*.app/Contents/SharedSupport/prefix/user.reg"),
    (HOME / "Applications", "*/*.app/Contents/SharedSupport/prefix/user.reg"),
]
WINE_SAVE = "drive_c/users/*/AppData/LocalLow/Orsoniks/CasualtiesUnknown/save.sv"


def find_wine():
    """every wine prefix with the game's progress or a run save in it"""
    out = []
    for root, pattern in BOTTLES:
        if not root.is_dir():
            continue
        for reg in sorted(root.glob(pattern)):
            prefix = reg.parent
            try:
                p = parse_reg(reg.read_text(errors="replace"))
            except OSError:
                continue
            runs = [f for f in prefix.glob(WINE_SAVE) if f.is_file()]
            save = max(runs, key=lambda f: f.stat().st_mtime) if runs else None
            if p or save:
                out.append({"prefix": prefix, "progress": p, "save": save})
    return out


def wine_running():
    # wine only writes user.reg every so often, so a running game might not be in it yet
    return subprocess.run(["pgrep", "-f", "CasualtiesUnknown.exe"], capture_output=True).returncode == 0


def import_wine(found, domain=DOMAIN, data=None):
    """pulls progress and the newest run save out of the bottles find_wine found.
    hands back the progress that changed and where the save went, None if it stayed"""
    incoming = {}
    for b in found:
        for k, v in b["progress"].items():
            incoming[k] = max(v, incoming.get(k, v))
    todo = merge(progress(prefs(domain)), incoming)
    for k, v in todo.items():
        subprocess.run(["defaults", "write", domain, k, "-int", str(v)], check=True)

    runs = [b["save"] for b in found if b["save"]]
    if not runs:
        return todo, None
    src = max(runs, key=lambda f: f.stat().st_mtime)
    dst = (data or saves.DATA[0]) / "save.sv"
    # same rule as saves.migrate. the newer run wins and the other one goes to backups
    if dst.exists():
        if dst.stat().st_mtime >= src.stat().st_mtime:
            return todo, None
        saves.backup(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return todo, dst
