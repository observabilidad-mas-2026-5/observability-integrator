import json, time, uuid, urllib.request, urllib.error, subprocess
from pathlib import Path
from urllib.parse import urlencode
out=Path('docs/evidence');out.mkdir(parents=True,exist_ok=True)
base='http://127.0.0.1:28000'
def request(path, method='GET', data=None, headers=None):
    req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data else None,method=method,headers={'Content-Type':'application/json',**(headers or {})})
    try:
        with urllib.request.urlopen(req,timeout=15) as r: return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code,json.loads(e.read())
def fetch(url):
    with urllib.request.urlopen(url,timeout=15) as r: return json.loads(r.read())
traceid=uuid.uuid4().hex
checks=[]
def check(name, ok):
    checks.append({'name':name,'passed':bool(ok)});assert ok,name
check('health',request('/health')==(200,{'status':'ok'}))
code,row=request('/credit-applications','POST',{'customer_name':'Synthetic evidence','document_number':'TEST','requested_amount':100},{'traceparent':'00-'+traceid+'-0123456789abcdef-01'})
check('create pending',code==201 and row['status']=='PENDING')
id=row['application_id']
check('read',request('/credit-applications/'+id)==(200,row))
check('list contains created',row in request('/credit-applications')[1])
check('update',request('/credit-applications/'+id+'/status','PUT',{'status':'APPROVED'})[1]['status']=='APPROVED')
check('missing 404',request('/credit-applications/missing')[0]==404)
check('validation 422',request('/credit-applications','POST',{'customer_name':'Test','document_number':'TEST','requested_amount':-1})[0]==422)
subprocess.run(['docker','compose','-f','compose.otel.yml','restart','service-b'],check=True)
for _ in range(40):
    try:
        code,persisted=request('/credit-applications/'+id)
        if code==200: break
    except Exception: pass
    time.sleep(1)
check('persistent after service-b restart',code==200 and persisted['status']=='APPROVED')
for _ in range(45):
    try:
        trace=fetch('http://127.0.0.1:26686/api/traces/'+traceid)
        if trace['data'] and len(trace['data'][0]['spans'])>5: break
    except Exception: pass
    time.sleep(1)
t=trace['data'][0]
services={v['serviceName'] for v in t['processes'].values()}
check('one trace across A B',{'service-a','service-b'}<=services)
check('postgres span',any(any(tag['key']=='db.system' and tag['value']=='postgresql' for tag in s['tags']) for s in t['spans']))
(out/'trace.json').write_text(json.dumps(trace,indent=2))
# Query through Grafana data source proxy: Loki remains internal to Compose.
auth=__import__('base64').b64encode(b'lab:local-lab-only').decode()
query='{service_name=~"service-a|service-b"} | trace_id="'+traceid+'"'
url='http://127.0.0.1:23000/api/datasources/proxy/uid/loki/loki/api/v1/query_range?'+urlencode({'query':query,'limit':100,'since':'15m'})
for _ in range(40):
    try:
        req=urllib.request.Request(url,headers={'Authorization':'Basic '+auth})
        with urllib.request.urlopen(req,timeout=15) as r: logs=json.loads(r.read())
        if len(logs['data']['result'])>=2: break
    except Exception: pass
    time.sleep(1)
check('correlated logs A B in Loki via Grafana',{'service-a','service-b'} <= {r['stream'].get('service_name') for r in logs['data']['result']})
(out/'logs.json').write_text(json.dumps(logs,indent=2))
for _ in range(15):
    targets=fetch('http://127.0.0.1:29090/api/v1/targets')
    if all(t['health']=='up' for t in targets['data']['activeTargets']): break
    time.sleep(1)
check('prometheus targets up',all(t['health']=='up' for t in targets['data']['activeTargets']))
(out/'targets.json').write_text(json.dumps(targets,indent=2))
req=urllib.request.Request('http://127.0.0.1:23000/api/dashboards/uid/credit-lab',headers={'Authorization':'Basic '+auth})
with urllib.request.urlopen(req) as r: dashboard=json.loads(r.read())
check('six panels provisioned',len(dashboard['dashboard']['panels'])==6)
(out/'validation.json').write_text(json.dumps({'trace_id':traceid,'application_id':id,'checks':checks},indent=2))
print(json.dumps({'trace_id':traceid,'passed':len(checks)},indent=2))
