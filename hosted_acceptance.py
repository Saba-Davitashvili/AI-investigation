"""Two-phase public deployment check with a disposable document.

Phase before saves a fixture/ID locally. Restart the HOSTED service yourself.
Phase after proves the same ID/text/version persists, then updates/deletes it.
Real provider/investigation evaluation is separate: evaluate_extended.py.
"""
import argparse
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from config import BASE_DIRECTORY


def api(path, method='GET', payload=None, multipart=False, auth=True):
    base=os.environ['EVALUATION_API_URL'].rstrip('/')
    if not base.startswith('https://'):
        raise ValueError('Hosted acceptance requires an HTTPS public URL.')
    headers={}
    if auth:
        credentials=f"{os.getenv('DEMO_USERNAME','reviewer')}:{os.environ['DEMO_PASSWORD']}".encode()
        headers['Authorization']='Basic '+base64.b64encode(credentials).decode()
    if multipart:
        boundary='trace-acceptance-'+uuid4().hex
        payload=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="hosted_acceptance.txt"\r\n'
                 'Content-Type: text/plain\r\n\r\n'+payload+f'\r\n--{boundary}--\r\n').encode()
        headers['Content-Type']='multipart/form-data; boundary='+boundary
    elif payload is not None:
        payload=json.dumps(payload).encode();headers['Content-Type']='application/json'
    request=Request(base+path, data=payload, method=method, headers=headers)
    with urlopen(request, timeout=180) as response:
        raw=response.read()
        return json.loads(raw) if raw else None


def main():
    load_dotenv(BASE_DIRECTORY/'.env')
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['before','after'])
    parser.add_argument('--state',type=Path,default=BASE_DIRECTORY/'reports/hosted_acceptance.json')
    args=parser.parse_args()
    base=os.environ['EVALUATION_API_URL'].rstrip('/')
    if args.phase=='before':
        if args.state.exists():
            raise SystemExit('Acceptance state exists. Use after, or choose a new --state path.')
        try:
            api('/documents',auth=False)
            raise RuntimeError('Documents endpoint is accessible without the demo credentials.')
        except HTTPError as error:
            if error.code!=401: raise
        health=api('/health')
        if health['source_documents']<50000:
            raise RuntimeError('Hosted corpus is below 50,000 documents.')
        marker='HOSTED'+uuid4().hex.upper()
        text=f'Synthetic deployment fixture. Project {marker} has budget 1200 GEL.'
        result=api('/documents','POST',text,True)
        doc=result['document']
        found=api('/search?q='+marker+'&mode=keyword&limit=20')['results']
        if not any(item['document']['parent_id']==doc['id'] for item in found):
            raise RuntimeError('Uploaded fixture is not searchable.')
        state={'status':'awaiting_hosted_restart','base_url':base,'before_utc':datetime.now(timezone.utc).isoformat(),
               'document':doc,'marker':marker,'health':health}
        args.state.parent.mkdir(parents=True,exist_ok=True)
        args.state.write_text(json.dumps(state,indent=2),encoding='utf-8')
        print('Before-restart checks passed. Restart the hosted Render service, then run phase after.')
    else:
        state=json.loads(args.state.read_text(encoding='utf-8'))
        if state['base_url']!=base or state['status']!='awaiting_hosted_restart':
            raise RuntimeError('State URL/status mismatch.')
        document_id=state['document']['id'];marker=state['marker']
        doc=api('/documents/'+document_id)
        for key in ['id','text','version','created_at']:
            if doc[key]!=state['document'][key]:
                raise RuntimeError('Persisted document differs after restart: '+key)
        found=api('/search?q='+marker+'&mode=keyword&limit=20')['results']
        if not any(item['document']['parent_id']==document_id for item in found):
            raise RuntimeError('Persisted document is not searchable after restart.')
        new_marker='UPDATED'+uuid4().hex.upper()
        updated=api('/documents/'+document_id,'PUT',f'Synthetic deployment fixture. Project {new_marker} has budget 1800 GEL.',True)
        if updated['document']['version']!=doc['version']+1:
            raise RuntimeError('Replacement did not increment version.')
        if api('/search?q='+marker+'&mode=keyword')['results']:
            raise RuntimeError('Stale keyword match after update.')
        for mode in ['keyword','semantic','hybrid']:
            found=api(f'/search?q={new_marker}&mode={mode}&limit=20')['results']
            if not any(item['document']['parent_id']==document_id for item in found):
                raise RuntimeError('Replacement not found in '+mode)
        api('/documents/'+document_id,'DELETE')
        for mode in ['keyword','semantic','hybrid']:
            found=api(f'/search?q={new_marker}&mode={mode}&limit=20')['results']
            if any(item['document']['parent_id']==document_id for item in found):
                raise RuntimeError('Deleted record remains in '+mode)
        state.update(status='passed_after_operator_reported_restart', after_utc=datetime.now(timezone.utc).isoformat(),
                     note='Operator must separately record actual Render restart time/build; this script cannot restart or independently attest that event.')
        args.state.write_text(json.dumps(state,indent=2),encoding='utf-8')
        print('Persistence, update and deletion checks passed. Record Render restart event and commit alongside this report.')


if __name__=='__main__':
    main()
