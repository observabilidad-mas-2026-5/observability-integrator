"""Assess existing measurements against objectives found in the reference ZIP."""
import json,zipfile,hashlib
from pathlib import Path
root=Path.cwd();out=root/'docs/evidence/reference';out.mkdir(parents=True,exist_ok=True)
record=json.loads((out/'zip-inventory.json').read_text(encoding='utf-8'))
assert hashlib.sha256(Path(record['path']).read_bytes()).hexdigest()==record['sha256'],'Original ZIP changed'
comparison=json.loads((root/'docs/evidence/benchmark.json').read_text(encoding='utf-8'))
results={}
for mode in ['without-otel','with-otel']:
 d=json.loads((root/'docs/evidence'/f'{mode}.json').read_text(encoding='utf-8'))['metrics']
 results[mode]={'p95_ms':d['http_req_duration']['p(95)'],'p99_ms':d['http_req_duration']['p(99)'],'error_rate':d['http_req_failed']['value'],'checks_rate':d['checks']['value'],'p95_lt_500':d['http_req_duration']['p(95)']<500,'p99_lt_1000':d['http_req_duration']['p(99)']<1000,'errors_lt_0_005':d['http_req_failed']['value']<0.005,'checks_ge_0_995':d['checks']['value']>=0.995}
results['cpu']={'observed_overhead_percent':comparison['comparison']['apps_cpu_percent']['percent'],'reference_goal_lt_5':comparison['comparison']['apps_cpu_percent']['percent']<5}
results['scope']='Retrospective assessment of saved five-minute paired benchmark; no new benchmark executed. Reference objectives, not universal industry guarantees.'
(out/'slo-assessment.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
