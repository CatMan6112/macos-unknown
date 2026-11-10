"""runs build/CU.app for N seconds (30 by default) with a log then quits it

usage: python3 -I scripts/run-test.py [seconds] [logname]
"""
import pathlib, subprocess, sys, time

root = pathlib.Path(__file__).resolve().parent.parent
secs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
log = root / "logs" / (sys.argv[2] if len(sys.argv) > 2 else "run.log")
exe = root / "build/CU.app/Contents/MacOS/CasualtiesUnknown"

# cwd = build/ so Steam finds steam_appid.txt
p = subprocess.Popen([str(exe), "-logFile", str(log)], cwd=root / "build")
for i in range(secs):
    time.sleep(1)
    if p.poll() is not None:
        print(f"exited early with code {p.returncode} after {i}s")
        break
else:
    p.terminate()
    print(f"ran {secs}s, terminated")
print(f"log: {log}")
