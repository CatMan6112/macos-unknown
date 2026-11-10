"""sums GPU time per encoder label for one process from an xctrace metal-gpu-intervals export

usage: python3 -I gpu-trace.py gpu.xml [process substring] [skip seconds]
"""
import sys, collections, xml.etree.ElementTree as ET

path = sys.argv[1]
want = sys.argv[2] if len(sys.argv) > 2 else "CasualtiesUnknown"
skip = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
ids = {}

def val(e):
    if e is None:
        return None
    if "ref" in e.attrib:
        return ids.get(e.attrib["ref"])
    v = (e.attrib.get("fmt"), e.text, e)
    if "id" in e.attrib:
        ids[e.attrib["id"]] = v
    for c in e:
        val(c)
    return v

tot = collections.Counter()
frames = set()
t0 = t1 = None
for ev, row in ET.iterparse(path):
    if row.tag != "row":
        continue
    cols = list(row)
    vals = [val(c) for c in cols]
    start = int(vals[0][1]); dur = int(vals[1][1])
    chan = vals[2][0]; frame = vals[3][1]
    label = vals[6][0] if vals[6] else ""
    proc = vals[10][0] if vals[10] else ""
    row.clear()
    if want not in (proc or "") or start < skip * 1e9:
        continue
    t0 = start if t0 is None else min(t0, start); t1 = max(t1 or 0, start + dur)
    frames.add(frame)
    tot[(chan, label.split("  (")[0])] += dur
n = max(len(frames), 1)
print(f"{n} frames over {(t1 - t0) / 1e9:.1f} s")
for (chan, label), d in tot.most_common(25):
    print(f"{d / n / 1e6:7.3f} ms/frame  {chan:9} {label[:110]}")
print(f"total {sum(tot.values()) / n / 1e6:.3f} ms/frame")
