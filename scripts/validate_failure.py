import json, subprocess, urllib.request, urllib.error, time, uuid
from pathlib import Path
compose=['docker','compose','-f','compose.otel.yml']
traceid=uuid.uuid4().hex
try:
    subprocess.run(compose+['stop','service-b'],check=True)
    req=urllib.request.Request('http://127.0.0.1:28000/credit-applications',headers={'traceparent':'00-'+traceid+'-0123456789abcdef-01'})
    try:
        urllib.request.urlopen(req,timeout=15)
        raise AssertionError('Expected 503')
    except urllib.error.HTTPError as e:
        payload=json.loads(e.read());assert e.code==503
        Path('docs/evidence/failure.json').write_text(json.dumps({'status':e.code,'body':payload,'trace_id':traceid},indent=2))
        print('Falla controlada: 503 confirmado')
finally:
    subprocess.run(compose+['up','-d','--wait','service-b'],check=True)
