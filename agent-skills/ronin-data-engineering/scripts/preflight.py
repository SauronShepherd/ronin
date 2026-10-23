#!/usr/bin/env python3
import argparse, json, os, shutil, subprocess, sys

TOP = {"doctor", "validate", "plan", "submit", "status", "logs", "evidence", "connectors"}
SUB = {"capabilities", "discover", "preview", "plan", "checkpoint-health"}

def run(exe, *args):
    return subprocess.run([exe, *args], text=True, capture_output=True, timeout=10)

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--ronin", default="ronin"); ap.add_argument("--json", action="store_true"); args=ap.parse_args()
    exe = shutil.which(args.ronin) if "/" not in args.ronin else args.ronin
    if not exe or not os.path.isfile(exe) or not os.access(exe, os.X_OK):
        print(json.dumps({"ok":False,"error":"ronin_not_found"})); return 2
    root=run(exe,"--help"); root_text=(root.stdout or "")+(root.stderr or "")
    conn=run(exe,"connectors","--help"); conn_text=(conn.stdout or "")+(conn.stderr or "")
    mt=sorted(x for x in TOP if x not in root_text); ms=sorted(x for x in SUB if x not in conn_text)
    result={"ok":root.returncode==0 and conn.returncode==0 and not mt and not ms,"missing_top":mt,"missing_connectors":ms}
    print(json.dumps(result,sort_keys=True) if args.json else result)
    return 0 if result["ok"] else 3
if __name__=="__main__": raise SystemExit(main())
