// Adaptación de los modos de la referencia para nuestros contratos de créditos.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
const mode = __ENV.MODE || 'normal';
const base = __ENV.BASE_URL || 'http://service-a:8000';
const vus = Number(__ENV.VUS || 50);
const unexpected = new Counter('unexpected_responses');
export const options = {
  scenarios: mode === 'spike' ? {
    spike: {executor:'ramping-vus',startVUs:vus,stages:[
      {duration:__ENV.RAMP || '15s',target:Number(__ENV.PEAK_VUS || 100)},
      {duration:__ENV.HOLD || '30s',target:Number(__ENV.PEAK_VUS || 100)},
      {duration:__ENV.RAMP || '15s',target:vus}],gracefulRampDown:'5s',gracefulStop:'5s'}
  } : {sustained:{executor:'constant-vus',vus:vus,duration:__ENV.DURATION || '5m',gracefulStop:'5s'}},
  summaryTrendStats:['avg','med','p(95)','p(99)','max'],
  thresholds: {checks:['rate>0.995'],unexpected_responses:['count==0'],
    http_req_failed:['rate<0.005'],
    ...(mode === 'normal' ? {http_req_duration:['p(95)<500','p(99)<1000']} : {})},
};
export function setup() {
  if (!['normal','errors','spike'].includes(mode)) throw new Error('MODE must be normal, errors or spike');
  const ids=[];
  const count=mode==='spike'?Number(__ENV.PEAK_VUS || 100):vus;
  for(let i=0;i<count;i++) {
    const r=http.post(base+'/credit-applications',JSON.stringify({customer_name:'Synthetic reference',document_number:'TEST',requested_amount:100}),{headers:{'Content-Type':'application/json'},tags:{name:'setup'}});
    if(r.status!==201) throw new Error('Cannot seed synthetic credits: '+r.status);
    ids.push(r.json('application_id'));
  }
  return {ids};
}
function expect(r,status) {
  const ok=check(r,{['expected '+status]:r=>r.status===status});
  unexpected.add(ok?0:1);
}
export default function(data) {
  const id=data.ids[(__VU-1)%data.ids.length];
  if(mode==='errors') {
    expect(http.get(base+'/credit-applications/missing-reference',{tags:{name:'expected_404'},responseCallback:http.expectedStatuses(404)}),404);
    expect(http.post(base+'/credit-applications',JSON.stringify({customer_name:'Synthetic',document_number:'TEST',requested_amount:-1}),{headers:{'Content-Type':'application/json'},tags:{name:'expected_422'},responseCallback:http.expectedStatuses(422)}),422);
  } else {
    expect(http.get(base+'/credit-applications/'+id,{tags:{name:'read'}}),200);
    expect(http.put(base+'/credit-applications/'+id+'/status',JSON.stringify({status:'APPROVED'}),{headers:{'Content-Type':'application/json'},tags:{name:'update'}}),200);
  }
  sleep(1);
}
