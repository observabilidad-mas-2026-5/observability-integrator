import json, time, uuid, urllib.request, urllib.error, subprocess
from pathlib import Path
from urllib.parse import urlencode
out=Path('docs/evidence/integrator');out.mkdir(parents=True,exist_ok=True)
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
subprocess.run(['docker','compose','-f','compose.otel.yml','restart','data-service'],check=True)
for _ in range(40):
    try:
        code,persisted=request('/credit-applications/'+id)
        if code==200: break
    except Exception: pass
    time.sleep(1)
check('persistent after data-service restart',code==200 and persisted['status']=='APPROVED')
for _ in range(45):
    try:
        trace=fetch('http://127.0.0.1:26686/api/traces/'+traceid)
        if trace['data'] and len(trace['data'][0]['spans'])>5: break
    except Exception: pass
    time.sleep(1)
t=trace['data'][0]
services={v['serviceName'] for v in t['processes'].values()}
check('one trace across A B data-service',{'service-a','service-b','data-service'}<=services)
check('postgres span',any(any(tag['key']=='db.system' and tag['value']=='postgresql' for tag in s['tags']) for s in t['spans']))
spans = {span['spanID']: span for span in t['spans']}
def service_of(span):
    return t['processes'][span['processID']]['serviceName']
def has_ancestor(span, service):
    visited = set()
    while span['spanID'] not in visited:
        visited.add(span['spanID'])
        parents = [spans[ref['spanID']] for ref in span['references']
                   if ref['refType'] == 'CHILD_OF' and ref['spanID'] in spans]
        if not parents:
            return False
        span = parents[0]
        if service_of(span) == service:
            return True
    return False
check('B child of A', any(service_of(span) == 'service-b' and has_ancestor(span, 'service-a') for span in spans.values()))
check('data-service child of B', any(service_of(span) == 'data-service' and has_ancestor(span, 'service-b') for span in spans.values()))
database_spans = [span for span in spans.values()
                  if any(tag['key'] == 'db.system.name' and tag['value'] == 'postgresql' for tag in span['tags'])]
check('SQL belongs to data-service', bool(database_spans) and all(
    service_of(span) == 'data-service' and has_ancestor(span, 'service-b') for span in database_spans))
check('SQL operation attributes', any(
    any(tag['key'] == 'db.operation.name' and tag['value'] == 'INSERT' for tag in span['tags'])
    for span in database_spans))
check('no SQL statements or parameters', all(
    tag['key'] not in {'db.statement', 'db.query.text', 'db.connection_string'}
    and not tag['key'].startswith('db.query.parameter')
    for span in database_spans for tag in span['tags']))
check('no synthetic PII in trace', 'Synthetic evidence' not in json.dumps(trace))
(out/'trace.json').write_text(json.dumps(trace,indent=2))
# Query through Grafana data source proxy: Loki remains internal to Compose.
auth=__import__('base64').b64encode(b'lab:local-lab-only').decode()
query='{service_name=~"service-a|service-b|data-service"} | trace_id="'+traceid+'"'
url='http://127.0.0.1:23000/api/datasources/proxy/uid/loki/loki/api/v1/query_range?'+urlencode({'query':query,'limit':100,'since':'15m'})
for _ in range(40):
    try:
        req=urllib.request.Request(url,headers={'Authorization':'Basic '+auth})
        with urllib.request.urlopen(req,timeout=15) as r: logs=json.loads(r.read())
        if len(logs['data']['result'])>=3: break
    except Exception: pass
    time.sleep(1)
check('correlated logs A B data-service in Loki via Grafana',{'service-a','service-b','data-service'} <= {r['stream'].get('service_name') for r in logs['data']['result']})
(out/'logs.json').write_text(json.dumps(logs,indent=2))
for _ in range(15):
    targets=fetch('http://127.0.0.1:29090/api/v1/targets')
    if all(t['health']=='up' for t in targets['data']['activeTargets']): break
    time.sleep(1)
check('prometheus targets up',all(t['health']=='up' for t in targets['data']['activeTargets']))
expected_instances = {'service-a:8000', 'service-b:8001', 'data-service:8002'}
check('three app scrape targets', expected_instances <= {
    target['labels'].get('instance') for target in targets['data']['activeTargets'] if target['health'] == 'up'})
metric_results = {}
for metric in ['http_requests_total{job="apps"}', 'credit_process_memory_bytes']:
    result = fetch('http://127.0.0.1:29090/api/v1/query?' + urlencode({'query': metric}))
    metric_results[metric] = result
    labels = [entry['metric'] for entry in result['data']['result']]
    if metric.startswith('http_requests'):
        check('HTTP metrics three services', expected_instances <= {label.get('instance') for label in labels})
    else:
        check('application metrics three services', {'service-a', 'service-b', 'data-service'} <= {
            label.get('service_name') for label in labels})
(out/'metrics.json').write_text(json.dumps(metric_results,indent=2))
(out/'targets.json').write_text(json.dumps(targets,indent=2))
req=urllib.request.Request('http://127.0.0.1:23000/api/dashboards/uid/credit-lab',headers={'Authorization':'Basic '+auth})
with urllib.request.urlopen(req) as r: dashboard=json.loads(r.read())
check('six panels provisioned',len(dashboard['dashboard']['panels'])==6)
(out/'validation.json').write_text(json.dumps({'trace_id':traceid,'application_id':id,'checks':checks},indent=2))
print(json.dumps({'trace_id':traceid,'passed':len(checks)},indent=2))
