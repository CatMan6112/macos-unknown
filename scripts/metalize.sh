#!/bin/zsh
# build/CU.app -> build/CU-metal.app. metal shaders from ShaderShell.app plus the
# API set to metal plus mac steam and symlinks so the game can find its loose files
set -e
ROOT=${0:A:h:h}
B="$ROOT/build"
[[ -e "$B/CU-metal.app" ]] && { echo "$B/CU-metal.app already exists; move it aside first"; exit 1; }
ditto "$B/CU.app" "$B/CU-metal.app"
"$ROOT/.venv/bin/python" -I "$ROOT/scripts/swap-shaders.py" \
  "$B/ShaderShell.app/Contents/Resources/Data" "$B/CU-metal.app/Contents/Resources/Data"
# mac steamworks dll and libsteam_api both come from build/SteamLib.app
S="$B/SteamLib.app/Contents"
[[ -d "$S" ]] || { echo "run scripts/build-steamlib.sh first"; exit 1; }
cp "$S/Resources/Data/Managed/com.rlabrecque.steamworks.net.dll" \
  "$B/CU-metal.app/Contents/Resources/Data/Managed/"
mkdir -p "$B/CU-metal.app/Contents/PlugIns"
ditto "$S/PlugIns/steam_api.bundle" "$B/CU-metal.app/Contents/PlugIns/steam_api.bundle"
# on mac Application.dataPath is Contents/ and not Contents/Resources/Data idk why the fuck
cd "$B/CU-metal.app/Contents"
ln -s Resources/Data/Lang Lang
ln -s Resources/Data/custommusic custommusic
cd "$B"
# Info.plist wants PlayerIcon.icns and the shell build doesnt have one
cp "$ROOT/patcher/assets/cu-apple.icns" "$B/CU-metal.app/Contents/Resources/PlayerIcon.icns"
codesign --force --deep -s - "$B/CU-metal.app"
echo "built $B/CU-metal.app"
