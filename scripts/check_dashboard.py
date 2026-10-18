import json, urllib.request
from pathlib import Path
from urllib.parse import urlencode
p=Path('otel/grafana/dashboards/credit-lab.json')
dashboard=json.loads(p.read_text(encoding='utf-8'));results=[]
for panel in dashboard['panels']:
    for target in panel['targets']:
        url='http://127.0.0.1:29090/api/v1/query?'+urlencode({'query':target['expr']})
        with urllib.request.urlopen(url,timeout=15) as response: data=json.load(response)
        assert data['status']=='success',(panel['title'],data)
        assert data['data']['result'],(panel['title'],'empty result')
        results.append({'panel':panel['title'],'query':target['expr'],'response':data})
# Require metrics that actually travelled SDK -> Collector -> Prometheus.
for metric in ['credit_process_memory_bytes','http_server_duration_milliseconds_count']:
    url='http://127.0.0.1:29090/api/v1/query?'+urlencode({'query':metric})
    with urllib.request.urlopen(url,timeout=15) as response: data=json.load(response)
    assert data['data']['result'],('OTLP SDK metric missing',metric)
    results.append({'metric':metric,'response':data})
Path('docs/evidence/dashboard-queries.json').write_text(json.dumps(results,indent=2))
print('Dashboard y métricas OTLP verificados:',len(results),'queries')
