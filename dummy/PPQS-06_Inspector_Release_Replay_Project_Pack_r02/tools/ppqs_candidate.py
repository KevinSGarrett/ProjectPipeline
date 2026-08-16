#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def rows(path):
    if not path.exists(): return []
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
def main():
    p=argparse.ArgumentParser(prog='ppqs-candidate')
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('self-check')
    sub.add_parser('show-intake')
    sub.add_parser('list-seed-jira')
    a=p.parse_args()
    manifest=ROOT/'PACK_MANIFEST.json'
    if a.cmd=='self-check':
        checks={
          'manifest':manifest.exists(),
          'brief':(ROOT/'BENCHMARK_BRIEF.md').exists() or (ROOT/'README.md').exists(),
          'seed_jira':(ROOT/'jira'/'seed'/'issues.jsonl').exists(),
          'oracle_paths_absent':not any('private_oracle' in str(x).lower() or 'gold_requirements' in x.name.lower() for x in ROOT.rglob('*')),
        }
        print(json.dumps({'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks},sort_keys=True))
        return 0 if all(checks.values()) else 1
    if a.cmd=='show-intake':
        print(manifest.read_text(encoding='utf-8')); return 0
    for row in rows(ROOT/'jira'/'seed'/'issues.jsonl'):
        print(json.dumps(row,sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
