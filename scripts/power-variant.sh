#!/bin/zsh
# power-variant.sh <name> <app> <json settings overrides> [player args...]
# throwaway home with my settings plus overrides. 10 s warmup then 15 s of macmon
# samples. prints mean GPU power/clock/busy/scaled load and CPU power
set -e
name=$1 app=$2 over=$3; shift 3
ROOT=${0:A:h:h}
O=${CUPORT_OUT:-$ROOT/out}/wintest/power; mkdir -p $O
H=$O/home-$name; S="$H/Library/Application Support/Orsoniks/CasualtiesUnknown"; mkdir -p "$S"
python3 -I - "$HOME/Library/Application Support/Orsoniks/CasualtiesUnknown/settings.json" "$S/settings.json" "$over" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); over = json.loads(sys.argv[3])
for s in d:
    if s["name"] in over: s["value"] = over[s["name"]]
json.dump(d, open(sys.argv[2], "w"))
PY
pid=
if [[ $app != idle ]]; then
  CFFIXED_USER_HOME=$H SteamAppId=4576490 MTL_HUD_ENABLED=0 "$app/Contents/MacOS/CasualtiesUnknown" "$@" -logFile $O/$name.log >/dev/null 2>&1 &
  pid=$!
  /bin/sleep 10
fi
macmon pipe -s 15 -i 1000 > $O/$name.jsonl
[[ -n $pid ]] && { screencapture -x $O/$name.png; kill -TERM $pid; wait $pid 2>/dev/null || true; }
python3 -I - $O/$name.jsonl "$name" "$(grep -o 'surface size [0-9x]*' $O/$name.log 2>/dev/null | tail -1)" <<'PY'
import json, sys, statistics as st
r = [json.loads(l) for l in open(sys.argv[1])][1:]
m = lambda k: st.mean(x[k] for x in r)
print(f"{sys.argv[2]:14} gpu {m('gpu_power'):5.2f} W @ {m('gpu_freq_mhz'):5.0f} MHz  busy {m('gpu_active_ratio'):4.0%}  load {m('gpu_scaled_ratio'):4.0%}  cpu {m('cpu_power'):5.2f} W  {sys.argv[3]}")
PY
/bin/sleep 3
