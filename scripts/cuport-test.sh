#!/bin/zsh
# cuport-test.sh <name> <app> '<json settings overrides>' [env assignments...]
# runs the app 12 s in a throwaway home with my settings plus the overrides,
# then dumps the [CUPort] log lines and grabs a screenshot
set -e
name=$1 app=$2 over=$3; shift 3
ROOT=${0:A:h:h}
O=${CUPORT_OUT:-$ROOT/out}/cuport; mkdir -p $O
[[ -x $O/winshot ]] || swiftc -O -o $O/winshot $ROOT/scripts/winshot.swift
H=$O/home-$name; S="$H/Library/Application Support/Orsoniks/CasualtiesUnknown"; mkdir -p "$S"
python3 -I - "$HOME/Library/Application Support/Orsoniks/CasualtiesUnknown/settings.json" "$S/settings.json" "$over" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); over = json.loads(sys.argv[3])
for s in d:
    if s["name"] in over: s["value"] = over[s["name"]]
json.dump(d, open(sys.argv[2], "w"), indent=2)
PY
# open it like a finder double click or the app never becomes active
envs=(--env CFFIXED_USER_HOME=$H); for e in "$@"; do envs+=(--env $e); done
rm -f $O/$name.log
open -n -W $envs "$app" --args -logFile $O/$name.log &
opener=$!
/bin/sleep 1
pid=$(pgrep -n -f "$app/Contents/MacOS/CasualtiesUnknown")
/bin/sleep ${WAIT:-12}
$O/winshot "Casualties Unknown" 2>&1 >/dev/null | sed "s/^/window /"
screencapture -x $O/$name.png
kill -TERM $pid; wait $opener 2>/dev/null || true
grep '\[CUPort\]' $O/$name.log || echo "no CUPort lines"
grep -i 'exception\|error' $O/$name.log | grep -iv steam | head -5
