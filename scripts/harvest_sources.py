"""Re-fetch the exact public sources into a new snapshot directory.

Usage: python scripts/harvest_sources.py --destination /path/to/new-snapshot
Copies metadata-only snapshots; downloads licensed immutable source bytes.
Never follows latest refs, downloads return panels, or runs source code.
"""
import argparse,hashlib,json,pathlib,shutil,time
import requests

def main():
    p=argparse.ArgumentParser();p.add_argument('--destination',required=True,type=pathlib.Path);p.add_argument('--source',help='Optional locked source prefix, for example qlib');a=p.parse_args()
    root=pathlib.Path(__file__).resolve().parents[1];dest=a.destination.resolve()
    if dest.exists():raise SystemExit('Destination already exists; choose an empty new snapshot path.')
    lock=json.loads((root/'datasets/raw/source_lock.json').read_text());lock=[x for x in lock if a.source is None or x['key'].split(':')[0]==a.source]
    if not lock:raise SystemExit('Unknown source prefix.')
    dest.mkdir(parents=True);failures=[]
    for x in lock:
        target=dest/x['path'];target.parent.mkdir(parents=True,exist_ok=True)
        try:
            if x['storage_policy']=='metadata_only':
                shutil.copy2(root/x['path'],target)
            else:
                for attempt in range(3):
                    try:
                        response=requests.get(x['url'],timeout=40,headers={'User-Agent':'GlobalFactorLibrary/0.1 public-source-research'});response.raise_for_status();content=response.content
                        break
                    except Exception:
                        if attempt==2:raise
                        time.sleep(1+attempt)
                if hashlib.sha256(content).hexdigest()!=x['sha256']:raise ValueError('Pinned source changed')
                target.write_bytes(content)
        except Exception as exc:failures.append({'key':x['key'],'error':str(exc)})
    (dest/'datasets/raw/source_lock.json').write_text(json.dumps(lock,ensure_ascii=False,indent=2))
    result={'expected_files':len(lock),'failed_files':failures,'status':'FAIL' if failures else 'PASS'}
    (dest/'harvest_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(bool(failures))

if __name__=='__main__':main()
