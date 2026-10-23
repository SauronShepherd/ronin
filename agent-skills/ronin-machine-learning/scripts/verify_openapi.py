#!/usr/bin/env python3
import argparse, json, pathlib, sys

REQUIRED_PREFIXES = ("/v1/ml-studio",)

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--openapi", required=True); ap.add_argument("--json", action="store_true"); args=ap.parse_args()
    try:
        doc=json.loads(pathlib.Path(args.openapi).read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"ok":False,"error":"invalid_openapi","detail":str(e)}) if args.json else f"invalid_openapi: {e}")
        return 2
    paths=doc.get("paths") if isinstance(doc,dict) else None
    if not isinstance(paths,dict):
        print(json.dumps({"ok":False,"error":"missing_paths"})); return 2
    matched=sorted(p for p in paths if p.startswith(REQUIRED_PREFIXES))
    ops=sum(sum(1 for m in v if m.lower() in {"get","post","put","delete","patch"}) for p,v in paths.items() if p.startswith(REQUIRED_PREFIXES) and isinstance(v,dict))
    result={"ok":bool(matched),"ml_paths":len(matched),"ml_operations":ops,"sample":matched[:10]}
    print(json.dumps(result,sort_keys=True) if args.json else result)
    return 0 if result["ok"] else 3
if __name__=="__main__": raise SystemExit(main())
