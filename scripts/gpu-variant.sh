#!/bin/zsh
# gpu-variant.sh <name> <app> <json overrides> [player args...]
# throwaway home with my settings.json plus overrides, records a 15 s metal
# system trace and prints GPU ms/frame
set -e
name=$1 app=$2 over=$3; shift 3
ROOT=${0:A:h:h}
O=${CUPORT_OUT:-$ROOT/out}/wintest/variants; mkdir -p $O
H=$O/home-$name; S="$H/Library/Application Support/Orsoniks/CasualtiesUnknown"
mkdir -p "$S"
python3 -I - "$HOME/Library/Application Support/Orsoniks/CasualtiesUnknown/settings.json" "$S/settings.json" "$over" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); over = json.loads(sys.argv[3])
for s in d:
    if s["name"] in over: s["value"] = over[s["name"]]
json.dump(d, open(sys.argv[2], "w"))
PY
T=$O/$name.trace
[[ -e $T ]] && { echo "$T exists"; exit 1; }
CFFIXED_USER_HOME=$H SteamAppId=4576490 xcrun xctrace record --template 'Metal System Trace' --time-limit 15s --output $T --launch -- "$app/Contents/MacOS/CasualtiesUnknown" "$@" -logFile $O/$name.log >/dev/null 2>&1 || true
pkill -f "$app/Contents/MacOS/CasualtiesUnknown" 2>/dev/null || true
xcrun xctrace export --input $T --xpath '/trace-toc/run[@number="1"]/data/table[@schema="metal-gpu-intervals"]' > $O/$name.xml
echo "== $name $over $(grep -o 'surface size [0-9x]*' $O/$name.log | tail -1)"
python3 -I $ROOT/scripts/gpu-trace.py $O/$name.xml CasualtiesUnknown 8 | sed -n '1p;2,7p;$p'
