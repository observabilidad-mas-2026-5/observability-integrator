"""Build and exercise cloud images entirely on local Docker, then stop own containers."""
import os, subprocess, json, uuid, time, urllib.request, urllib.error, base64
from pathlib import Path
root=Path.cwd();e=root/'docs/evidence';images={};containers={}
def run(cmd):
    r=subprocess.run(cmd,text=True,capture_output=True)
    if r.returncode: raise RuntimeError(r.stderr+r.stdout)
    return r.stdout.strip()
for name in ['collector','prometheus','loki','grafana','gateway']:
    tag='observability-integrator-'+name+':local'
    images[name]={'tag':tag,'id':run(['docker','build','--quiet','-f',f'infra/images/{name}.Dockerfile','-t',tag,'.'])}
(e/'cloud-image-builds.json').write_text(json.dumps(images,indent=2))
runid=uuid.uuid4().hex[:8]
def start(name,image,args=(),env=None,shared=True):
    cmd=['docker','run','--rm','-d','--name','observability-integrator-cloud-smoke-'+runid+'-'+name,'--label','codex.lab=observability-integrator-cloud-smoke']
    if shared: cmd+=['--network','container:'+containers['jaeger']]
    else:cmd+=['--network','observability-integrator_default','-p','127.0.0.1:28080:8080']
    for k,v in (env or {}).items():cmd+=['-e',k+'='+v]
    id=run(cmd+[image]+list(args));containers[name]=id
base='http://127.0.0.1:28080'
def fetch(path, method='GET', data=None, auth=False):
    headers={'Content-Type':'application/json'}
    if auth:headers['Authorization']='Basic '+base64.b64encode(b'lab:local-lab-only').decode()
    req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data else None,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)
try:
    start('jaeger','jaegertracing/all-in-one:1.64.0',['--collector.otlp.grpc.host-port=0.0.0.0:14317','--collector.otlp.http.host-port=0.0.0.0:14318'],{'COLLECTOR_OTLP_ENABLED':'true','QUERY_BASE_PATH':'/jaeger'},shared=False)
    for name in ['loki','collector','prometheus']:start(name,images[name]['tag'])
    start('grafana',images['grafana']['tag'],env={'GF_SECURITY_ADMIN_USER':'lab','GF_SECURITY_ADMIN_PASSWORD':'local-lab-only','GF_SERVER_ROOT_URL':'%(protocol)s://%(domain)s/grafana/','GF_SERVER_SERVE_FROM_SUB_PATH':'true'})
    common={'OTEL_ENABLED':'true','OTEL_EXPORTER_OTLP_ENDPOINT':'http://127.0.0.1:4318'}
    start('service-b','observability-integrator-api:local',['uvicorn','app.storage:app','--host','0.0.0.0','--port','8001'],dict(common,OTEL_SERVICE_NAME='service-b-cloud-smoke',DATABASE_URL='postgresql+psycopg://lab:local-lab-only@postgres:5432/credits'))
    start('service-a','observability-integrator-api:local',env=dict(common,OTEL_SERVICE_NAME='service-a-cloud-smoke',SERVICE_B_URL='http://127.0.0.1:8001'))
    start('gateway',images['gateway']['tag'])
    for _ in range(60):
        try:
            if fetch('/health')['status']=='ok' and fetch('/grafana/api/health')['database']=='ok':break
        except Exception:pass
        time.sleep(1)
    else:raise RuntimeError('Cloud bundle health timeout')
    req=urllib.request.Request(base+'/credit-applications',method='POST',headers={'Content-Type':'application/json','traceparent':'00-'+runid.ljust(32,'a')+'-0123456789abcdef-01'},data=json.dumps({'customer_name':'Cloud smoke synthetic','document_number':'TEST','requested_amount':100}).encode())
    with urllib.request.urlopen(req) as response:row=json.load(response)
    assert row['status']=='PENDING'
    assert fetch('/credit-applications/'+row['application_id'])==row
    traceid=runid.ljust(32,'a')
    for _ in range(30):
        try:
            traces=fetch('/jaeger/api/traces/'+traceid)
            if traces['data']:break
        except urllib.error.HTTPError as exc:
            if exc.code!=404:raise
        time.sleep(1)
    assert traces['data']
    services={p['serviceName'] for p in traces['data'][0]['processes'].values()}
    assert {'service-a-cloud-smoke','service-b-cloud-smoke'}<=services
    for _ in range(20):
        targets=fetch('/prometheus/api/v1/targets')
        if all(t['health']=='up' for t in targets['data']['activeTargets']):break
        time.sleep(1)
    assert all(t['health']=='up' for t in targets['data']['activeTargets'])
    dashboard=fetch('/grafana/api/dashboards/uid/credit-lab',auth=True)
    assert len(dashboard['dashboard']['panels'])==6
    (e/'cloud-bundle-local.json').write_text(json.dumps({'scope':'local Docker only; not a cloud deployment','trace_id':traceid,'services':sorted(services),'targets':targets,'grafana_panels':len(dashboard['dashboard']['panels'])},indent=2))
    print('Cloud images and loopback bundle: locally validated, no cloud deployment.')
finally:
    # IDs belong only to this run. --rm removes transient test containers, not the lab DB.
    for name,id in reversed(list(containers.items())):
        logs=subprocess.run(['docker','logs','--tail','15',id],capture_output=True,text=True)
        (e/('cloud-smoke-'+name+'.log')).write_text(logs.stdout+logs.stderr)
        subprocess.run(['docker','stop','-t','2',id],capture_output=True)
