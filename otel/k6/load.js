import http from 'k6/http';
import { check, sleep } from 'k6';
export const options = {
  vus: Number(__ENV.VUS || 50), duration: __ENV.DURATION || '5m',
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(95)', 'p(99)'],
  thresholds: {http_req_failed: ['rate<0.01'], checks: ['rate>0.99']},
};
const base = __ENV.BASE_URL || 'http://service-a:8000';
export default function () {
  // Bounded dataset: reuse one application per VU, avoiding unbounded list/DB growth.
  let id = __ENV.SEED_ID;
  if (!id) {
    const r = http.post(base+'/credit-applications', JSON.stringify({customer_name:'Synthetic',document_number:'TEST',requested_amount:100}), {headers:{'Content-Type':'application/json'},tags:{name:'create'}});
    check(r, {'created': r=>r.status===201});
    if (r.status!==201) {sleep(1); return;}
    id=r.json('application_id');
  }
  const r=http.get(base+'/credit-applications/'+id, {tags:{name:'read'}});
  check(r, {'read':r=>r.status===200});
  const u=http.put(base+'/credit-applications/'+id+'/status',JSON.stringify({status:'APPROVED'}),{headers:{'Content-Type':'application/json'},tags:{name:'update'}});
  check(u, {'updated':r=>r.status===200});
  sleep(1);
}
