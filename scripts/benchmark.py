"""Sequential 50 VU x 5 min paired benchmark; never contacts a cloud."""
import os, json, time, subprocess, urllib.request, statistics, re, csv
from datetime import datetime, timezone
from pathlib import Path
compose=['docker','compose','-f','compose.otel.yml']
out=Path('docs/evidence');out.mkdir(parents=True,exist_ok=True)
def run(args, env=None): return subprocess.run(compose+args,check=True,env=env,text=True,capture_output=True)
def mib(s):
    value,unit=re.match(r'([0-9.]+)\s*(\w+)',s).groups()
    return float(value)*{'B':1/1048576,'KiB':1/1024,'MiB':1,'GiB':1024,'kB':1000/1048576,'MB':1000000/1048576,'GB':1000000000/1048576}[unit]
body=json.dumps({'customer_name':'Benchmark synthetic','document_number':'TEST','requested_amount':100}).encode()
req=urllib.request.Request('http://127.0.0.1:28000/credit-applications',data=body,headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req) as r: seed=json.load(r)['application_id']
results={}
try:
 for enabled,label in [('false','without-otel'),('true','with-otel')]:
    env=dict(os.environ,OTEL_ENABLED=enabled)
    run(['up','-d','--wait','service-a','service-b'],env)
    print(label+': warmup 20s',flush=True)
    run(['run','--rm','-e','DURATION=20s','-e','VUS=50','-e','SEED_ID='+seed,'k6','run','/scripts/load.js'],env)
    ids={s:run(['ps','-q',s]).stdout.strip() for s in ['service-a','service-b','collector']}
    rows=[];started=datetime.now(timezone.utc).isoformat()
    with (out/(label+'.log')).open('w') as log:
        proc=subprocess.Popen(compose+['run','--rm','-e','DURATION=5m','-e','VUS=50','-e','SEED_ID='+seed,'k6','run','--summary-export=/results/'+label+'.json','/scripts/load.js'],env=env,stdout=log,stderr=subprocess.STDOUT)
        while proc.poll() is None:
            stamp=datetime.now(timezone.utc).isoformat()
            stats=subprocess.run(['docker','stats','--no-stream','--format','{{json .}}',*ids.values()],text=True,capture_output=True,check=True)
            for line in stats.stdout.splitlines():
                data=json.loads(line)
                service=next((s for s,id in ids.items() if id.startswith(data['ID'])),None)
                if service: rows.append({'timestamp':stamp,'service':service,'cpu_percent':float(data['CPUPerc'].rstrip('%')),'memory_mib':mib(data['MemUsage'].split('/')[0].strip())})
            time.sleep(3)
        if proc.returncode: raise RuntimeError(label+' k6 failed; see log')
    with (out/(label+'-resources.csv')).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['timestamp','service','cpu_percent','memory_mib']);writer.writeheader();writer.writerows(rows)
    summary=json.loads((out/(label+'.json')).read_text(encoding='utf-8'))
    groups={s:[r for r in rows if r['service']==s] for s in ids}
    results[label]={'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),'p99_ms':summary['metrics']['http_req_duration']['p(99)'],'requests':summary['metrics']['http_reqs']['count'],'failed_rate':summary['metrics']['http_req_failed']['value'],'resources':{s:{'samples':len(rs),'cpu_mean_percent':statistics.mean(r['cpu_percent'] for r in rs),'memory_mean_mib':statistics.mean(r['memory_mib'] for r in rs)} for s,rs in groups.items()}}
    print(label+': '+str(results[label]['p99_ms'])+' ms p99',flush=True)
finally:
 run(['up','-d','--wait','service-a','service-b'],dict(os.environ,OTEL_ENABLED='true'))
base=results['without-otel'];obs=results['with-otel']
def delta(a,b): return {'absolute':b-a,'percent':(b-a)/a*100 if a else None}
results['comparison']={'p99_ms':delta(base['p99_ms'],obs['p99_ms']), 'apps_cpu_percent':delta(sum(base['resources'][s]['cpu_mean_percent'] for s in ['service-a','service-b']),sum(obs['resources'][s]['cpu_mean_percent'] for s in ['service-a','service-b'])), 'apps_memory_mib':delta(sum(base['resources'][s]['memory_mean_mib'] for s in ['service-a','service-b']),sum(obs['resources'][s]['memory_mean_mib'] for s in ['service-a','service-b']))}
results['conditions']={'vus':50,'duration':'5m per mode','warmup':'20s per mode','pairs':1,'seed_id':seed,'collector':'running in both modes; baseline receives no application OTLP','app_limits':'each 1 CPU / 512 MiB','resource_sampling':'docker stats every ~5s, mean per service','limitations':'single ordered pair; no statistical significance; other local containers remain active'}
(out/'benchmark.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results['comparison'],indent=2))
