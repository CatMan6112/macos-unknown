"""sums up powermetrics + top samples for named time windows

usage: python3 -I scripts/bench-report.py <bench dir> name [name...]
each name needs <name>-window.txt (start/end lines) and <name>-top.txt
"""
import re, sys, pathlib, statistics as st
from datetime import datetime

d = pathlib.Path(sys.argv[1])
pm = (d / "powermetrics.txt").read_text(errors="replace")
samples = []
for block in pm.split("*** Sampled system activity (")[1:]:
    ts = datetime.strptime(block[:24], "%a %b %d %H:%M:%S %Y")
    def mw(label):
        m = re.search(label + r": (\d+) mW", block)
        return int(m.group(1)) if m else None
    samples.append((ts, mw("CPU Power"), mw("GPU Power"), mw(r"Combined Power \(CPU \+ GPU \+ ANE\)")))

def window(name):
    a, b = (d / f"{name}-window.txt").read_text().split("\n")[:2]
    year = samples[0][0].year
    p = lambda s: datetime.strptime(f"{year} {s.strip()}", "%Y %a %b %d %H:%M:%S")
    return p(a), p(b)

def top_cpu(name):
    # mean %CPU and POWER per process. first top frame gets skipped cause its junk
    frames = (d / f"{name}-top.txt").read_text().split("Processes:")[2:]
    procs = {}
    for f in frames:
        for line in f.splitlines():
            m = re.match(r"\s*(\d+)\s+(.+?)\s+([\d.]+)\s+([\d.]+)\s*$", line)
            if m:
                key = m.group(2).strip()
                c, pw = procs.setdefault(key, ([], []))
                c.append(float(m.group(3))); pw.append(float(m.group(4)))
    n = len(frames)
    return n, sorted(((sum(c)/n, sum(pw)/n, k) for k, (c, pw) in procs.items()), reverse=True)

for name in sys.argv[2:]:
    a, b = window(name)
    sel = [s for s in samples if a <= s[0] <= b]
    print(f"== {name}  {a:%H:%M:%S}-{b:%H:%M:%S}  {len(sel)} powermetrics samples")
    for i, lab in ((1, "CPU"), (2, "GPU"), (3, "Combined")):
        v = [s[i] for s in sel if s[i] is not None]
        if v:
            print(f"  {lab:9s} mean {st.mean(v)/1000:6.2f} W  median {st.median(v)/1000:6.2f} W  max {max(v)/1000:6.2f} W")
    n, rows = top_cpu(name)
    print(f"  top ({n} frames), mean %CPU / energy impact:")
    for c, pw, k in rows[:8]:
        print(f"    {c:6.1f}%  {pw:6.1f}  {k}")
