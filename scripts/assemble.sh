#!/bin/zsh
# builds build/CU.app, Shell.app plus a copy of the game data with the windows
# bits swapped out. only reads the crossover install, never writes to it
set -e
ROOT=${0:A:h:h}
B="$ROOT/build"
# point CU_DATA at your own CasualtiesUnknown_Data if its not in a crossover bottle called Steam
G=${CU_DATA:-"$HOME/Library/Application Support/CrossOver/Bottles/Steam/drive_c/Program Files (x86)/Steam/steamapps/common/Casualties Unknown/CasualtiesUnknown_Data"}
[[ -d "$G" ]] || { echo "game data not found: $G"; exit 1; }
[[ -e "$B/CU.app" ]] && { echo "$B/CU.app already exists; move it aside first"; exit 1; }

ditto "$B/Shell.app" "$B/CU.app"
R="$B/CU.app/Contents/Resources"
mv "$R/Data" "$R/Data.shell"
ditto "$G" "$R/Data"
D="$R/Data"

# windows native plugins (steam_api64, NativeNamedPipe, Burst) are useless here
rm -rf "$D/Plugins"

# builtin resources come from the shell build, those are the metal ones
cp "$R/Data.shell/Resources/unity_builtin_extra" "$D/Resources/unity_builtin_extra"
cp "$R/unity default resources" "$D/Resources/unity default resources"

# the game ships windows class libs that P/Invoke kernel32, swap in the mac ones
for f in "$R"/Data.shell/Managed/(mscorlib|System|Mono|netstandard)*.dll(N); do
  cp "$f" "$D/Managed/${f:t}"
done

echo 4576490 > "$B/steam_appid.txt"
codesign --force --deep -s - "$B/CU.app"
echo "assembled $B/CU.app"
