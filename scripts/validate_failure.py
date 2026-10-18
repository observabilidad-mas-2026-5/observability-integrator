import json, subprocess, urllib.request, urllib.error, time, uuid
from pathlib import Path
compose=['docker','compose','-f','compose.otel.yml']
out=Path('docs/evidence/integrator');out.mkdir(parents=True,exist_ok=True)
results=[]
for dependency in ['data-service','service-b']:
    traceid=uuid.uuid4().hex
    try:
        subprocess.run(compose+['stop',dependency],check=True)
        req=urllib.request.Request('http://127.0.0.1:28000/credit-applications',headers={'traceparent':'00-'+traceid+'-0123456789abcdef-01'})
        try:
            urllib.request.urlopen(req,timeout=15)
            raise AssertionError('Expected 503')
        except urllib.error.HTTPError as error:
            payload=json.loads(error.read());assert error.code==503
            results.append({'dependency':dependency,'status':error.code,'body':payload,'trace_id':traceid})
            print(dependency+': 503 confirmado')
    finally:
        subprocess.run(compose+['up','-d','--wait',dependency],check=True)
        (out/'failure.json').write_text(json.dumps(results,indent=2))
