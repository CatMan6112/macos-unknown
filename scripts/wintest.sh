#!/bin/zsh
# wintest.sh <name> <app> [player args...]
# launch, wait 10 s, sample GPU use and game CPU every second for 20 s, screenshot,
# quit. results land in out/wintest, or $CUPORT_OUT/wintest
set -e
name=$1 app=$2; shift 2
ROOT=${0:A:h:h}
O=${CUPORT_OUT:-$ROOT/out}/wintest; mkdir -p $O
exe="$app/Contents/MacOS/CasualtiesUnknown"
start=$(date '+%Y-%m-%d %H:%M:%S')
SteamAppId=4576490 MTL_HUD_ENABLED=${HUD:-0} MTL_HUD_LOG_ENABLED=1 "$exe" "$@" -logFile "$O/$name.log" >/dev/null 2>&1 &
pid=$!
/bin/sleep 10
: > "$O/$name.samples"
for i in {1..20}; do
  g=$(ioreg -r -d 1 -c IOAccelerator | grep -o '"Device Utilization %"=[0-9]*' | head -1 | cut -d= -f2)
  c=$(ps -o pcpu= -p $pid | tr -d ' ')
  w=$(ps -Ao pcpu,comm | awk '/WindowServer$/{print $1}')
  echo "$g $c $w" >> "$O/$name.samples"
  /bin/sleep 1
done
screencapture -x "$O/$name.png"
kill -TERM $pid; wait $pid 2>/dev/null || true
log show --start "$start" --style compact --predicate 'process == "CasualtiesUnknown" AND (eventMessage CONTAINS[c] "fps" OR eventMessage CONTAINS[c] "frame")' 2>/dev/null | tail -n +2 > "$O/$name.hud" || true
awk -v n=$name '{g+=$1;c+=$2;w+=$3;k++} END{printf "%-14s gpu %3.0f%%  game cpu %4.0f%%  windowserver %4.0f%%\n",n,g/k,c/k,w/k}' "$O/$name.samples"
grep -E 'surface size|RecreateSurface' "$O/$name.log" | tail -2
echo "hud lines: $(wc -l < $O/$name.hud)"
