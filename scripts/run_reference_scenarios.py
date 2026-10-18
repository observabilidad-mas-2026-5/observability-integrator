"""Short local functional runs, not a replacement for the five-minute benchmark."""
import subprocess,json
from pathlib import Path
root=Path.cwd();out=root/'docs/evidence/reference';out.mkdir(parents=True,exist_ok=True)
results=[]
for mode in ['normal','errors','spike']:
 cmd=['docker','compose','-f','compose.otel.yml','run','--rm','-e','MODE='+mode,'-e','VUS=10','-e','DURATION=20s','-e','PEAK_VUS=20','-e','RAMP=10s','-e','HOLD=10s','k6','run','--summary-export=/results/reference/k6-'+mode+'.json','/scripts/scenarios.js']
 run=subprocess.run(cmd,text=True,capture_output=True)
 (out/('k6-'+mode+'.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
 if run.returncode not in [0,99]:raise RuntimeError(mode+': k6 failed to execute; see log')
 d=json.loads((out/('k6-'+mode+'.json')).read_text(encoding='utf-8'))
 assert d['metrics']['unexpected_responses']['count']==0,mode
 assert d['metrics']['checks']['value']==1,mode
 results.append({'mode':mode,'exit_code':run.returncode,'vus':10,'peak_vus':20 if mode=='spike' else 10,'configured_duration':'30s ramp/hold/ramp' if mode=='spike' else '20s','requests':d['metrics']['http_reqs']['count'],'p99_ms':d['metrics']['http_req_duration']['p(99)'],'http_failed_rate':d['metrics']['http_req_failed']['value'],'all_expected_statuses':True,'scope':'functional smoke; no CPU/memory benchmark or statistical SLO conclusion'})
 print(mode+': expected statuses validated; k6 exit '+str(run.returncode),flush=True)
(out/'k6-scenarios.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
