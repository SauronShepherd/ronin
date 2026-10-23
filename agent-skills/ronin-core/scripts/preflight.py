#!/usr/bin/env python3
import argparse, json, os, shutil, subprocess, sys

REQUIRED = {"doctor", "validate", "plan", "submit", "status", "logs", "evidence", "jobs", "cancel"}

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ronin", default="ronin")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    exe = shutil.which(args.ronin) if "/" not in args.ronin else args.ronin
    if not exe or not os.path.isfile(exe) or not os.access(exe, os.X_OK):
        result = {"ok": False, "error": "ronin_not_found", "missing": sorted(REQUIRED)}
        print(json.dumps(result) if args.json else "Ronin CLI not found", file=sys.stdout)
        return 2
    cp = subprocess.run([exe, "--help"], text=True, capture_output=True, timeout=10)
    text = (cp.stdout or "") + "\n" + (cp.stderr or "")
    present = sorted(cmd for cmd in REQUIRED if cmd in text)
    missing = sorted(REQUIRED - set(present))
    result = {"ok": cp.returncode == 0 and not missing, "executable": exe, "present": present, "missing": missing}
    print(json.dumps(result, sort_keys=True) if args.json else f"present={present} missing={missing}")
    return 0 if result["ok"] else 3

if __name__ == "__main__":
    raise SystemExit(main())
