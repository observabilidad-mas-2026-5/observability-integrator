import json,base64,urllib.request,hashlib,subprocess
from pathlib import Path
from urllib.parse import urlencode
root=Path.cwd();out=root/'docs/evidence/integrator/reference';out.mkdir(parents=True,exist_ok=True)
auth='Basic '+base64.b64encode(b'lab:local-lab-only').decode()
def fetch(path):
    req=urllib.request.Request('http://127.0.0.1:23000'+path,headers={'Authorization':auth})
    with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)
loki=fetch('/api/datasources/uid/loki')['jsonData'];jaeger=fetch('/api/datasources/uid/jaeger')['jsonData']
assert loki['derivedFields'][0]['url']=='${__value.raw}','Grafana interpolated away the derived URL'
query=jaeger['tracesToLogsV2']['query'];assert '${__span.traceId}' in query
traceid=json.loads((root/'docs/evidence/integrator/validation.json').read_text(encoding='utf-8'))['trace_id']
trace=fetch('/api/datasources/proxy/uid/jaeger/api/traces/'+traceid)['data'][0]
start=min(s['startTime'] for s in trace['spans'])*1000-60_000_000_000
end=max(s['startTime']+s['duration'] for s in trace['spans'])*1000+60_000_000_000
resolved=query.replace('${__span.traceId}',traceid)
logs=fetch('/api/datasources/proxy/uid/loki/loki/api/v1/query_range?'+urlencode({'query':resolved,'start':start,'end':end,'limit':100}))
services={r['stream'].get('service_name') for r in logs['data']['result']}
assert {'service-a','service-b','data-service'}<=services
span_services={span['spanID']:trace['processes'][span['processID']]['serviceName'] for span in trace['spans']}
assert all(result['stream'].get('trace_id')==traceid and
           span_services.get(result['stream'].get('span_id'))==result['stream'].get('service_name')
           for result in logs['data']['result']), 'Log span does not belong to the traced service'
id=subprocess.check_output(['docker','compose','-f','compose.otel.yml','ps','-q','service-a'],text=True).strip()
image_hashes=json.loads(subprocess.check_output(['docker','exec',id,'python','-c',"import hashlib,pathlib,json; print(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pathlib.Path('/app/app').glob('*.py')}))"],text=True))
local_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'app').glob('*.py')}
assert local_hashes==image_hashes,'API differs from the previously validated image'
result={'trace_id':traceid,'grafana_runtime_templates_preserved':True,'log_to_trace_template':loki['derivedFields'][0],'trace_to_logs_config':jaeger['tracesToLogsV2'],'resolved_logql':resolved,'services_with_logs':sorted(services),'logs':logs,'api_unchanged_matches_running_image':True,'api_sha256':local_hashes,'scope':'Grafana provisioning and backend correlation tested; visual navigation assessed separately'}
(out/'correlation-runtime.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('Templates, Jaeger/Loki correlation and unchanged API: verified.')
