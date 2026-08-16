#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
LOCK=json.loads((ROOT/'UPSTREAM_LOCK.json').read_text(encoding='utf-8'))
def run(cmd,cwd=None): return subprocess.run(cmd,cwd=cwd,check=True,text=True)
def main():
    p=argparse.ArgumentParser(); p.add_argument('--destination',default=str(ROOT.parent/'seed_repository'/'upstream')); a=p.parse_args()
    dst=Path(a.destination).resolve()
    if dst.exists(): shutil.rmtree(dst)
    dst.parent.mkdir(parents=True,exist_ok=True)
    run(['git','clone','--no-checkout',LOCK['repository'],str(dst)])
    run(['git','checkout','--detach',LOCK['baseline_commit']],cwd=dst)
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dst,text=True).strip()
    if actual!=LOCK['baseline_commit']:
        raise SystemExit(f'baseline mismatch: expected {LOCK["baseline_commit"]}, got {actual}')
    print(json.dumps({'status':'PASS','head':actual,'destination':str(dst)},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
