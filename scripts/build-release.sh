#!/bin/zsh
# packs the launcher into build/release/MacOS Unknown.app + a zip for github
# version defaults to VERSION in launcher.py
# ARCH=x86_64 builds an intel launcher into build/release-x86_64 from .venv-x64
# .venv wheels are arm64 only so make .venv-x64 with arch -x86_64 python3 -m venv
set -e
ROOT=${0:A:h:h}
cd "$ROOT"
OUT=build/release
VENV=.venv RUN=() TAG=
if [[ $ARCH == x86_64 ]]; then
  OUT=build/release-x86_64 VENV=.venv-x64 RUN=(arch -x86_64) TAG=-intel
fi
NAME="MacOS Unknown"
APP="$OUT/dist/$NAME.app"

VER=${1:-$(sed -n 's/^VERSION = "\(.*\)"/\1/p' patcher/launcher.py)}
grep -q "^VERSION = \"$VER\"" patcher/launcher.py || { echo "launcher.py VERSION isnt $VER, bump it first"; exit 1; }

[[ -e $OUT ]] && { echo "$OUT already exists, move it aside first"; exit 1; }
mkdir -p $OUT

$RUN $VENV/bin/pyinstaller --noconfirm --windowed --name "$NAME" \
  --icon "$ROOT/patcher/assets/cu-apple.icns" \
  --osx-bundle-identifier dev.catman6112.macos-unknown \
  --add-data "$ROOT/patcher/assets:assets" \
  --collect-all UnityPy \
  --workpath $OUT/work --specpath $OUT --distpath $OUT/dist \
  "$ROOT/patcher/launcher.py"

# pyinstaller splits nested .apps apart and breaks their signatures, so ditto the payload in after
# real files in Resources, symlink in Frameworks (thats _MEIPASS), same as pyinstaller does
ditto patcher/payload "$APP/Contents/Resources/payload"
ln -s ../Resources/payload "$APP/Contents/Frameworks/payload"

# resign just the outer app so the payload keeps its own signatures
codesign --force -s - "$APP"
codesign --verify --deep --strict "$APP"
codesign --verify --deep --strict "$APP/Contents/Resources/payload/Shell.app"

ditto -c -k --keepParent "$APP" "$OUT/MacOS-Unknown-$VER$TAG.zip"
du -sh "$APP" "$OUT/MacOS-Unknown-$VER$TAG.zip"
