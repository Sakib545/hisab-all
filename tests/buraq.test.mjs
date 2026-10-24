import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {settlement,courierSummary,productReport,bankAnalytics,searchTx} from '../lib/buraq.ts';
const orders=JSON.parse(readFileSync(new URL('./fixtures-orders.json',import.meta.url))).records.order;
const truth=JSON.parse(readFileSync(new URL('./fixture-settlement-truth.json',import.meta.url)));
const rtruth=JSON.parse(readFileSync(new URL('./fixture-returns-truth.json',import.meta.url)));
test('site settlement == Smart Product bot settlement (real bot output)',()=>{
  const s=settlement(orders);
  for (const k of ['total_parcels','total_cod','delivered_parcels','delivered_cod','return_parcels','return_cod','pending_parcels','pending_cod','total_charge','expected_settlement','matched_payout','matched_collected','remaining']) assert.equal(s[k],truth[k],k);
  assert.deepEqual(s.products,truth.products);
});
test('site return report == bot courier_summary',()=>{const c=courierSummary(orders);for(const k of Object.keys(rtruth))assert.equal(c[k],rtruth[k],k)});
test('product report by date range',()=>{const all=productReport(orders);assert.equal(all.orders,40);assert.equal(all.cod,35250);const oct=productReport(orders,'2026-10-01','2026-10-31');assert.equal(oct.orders,22)});
test('bank analytics + search',()=>{const tx=[{a:4000000,d:{account:'111',bank:'IFIC',payment_month:'2026-09',reference:'IF001',date:'2026-09-28'}},{a:1000000,d:{account:'222',bank:'PUBALI',payment_month:'2026-10',reference:'PB9',date:'2026-10-01'}},{a:500000,d:{account:'111',bank:'IFIC',payment_month:'2026-10',reference:'IF2',date:'2026-10-02'}}];
  const a=bankAnalytics(tx,2);assert.equal(a.total,5500000);assert.equal(a.top[0].key,'111');assert.equal(a.top[0].n,2);assert.deepEqual(a.byMonth.map(m=>m.key),['2026-09','2026-10']);
  assert.equal(searchTx(tx,'pb9').length,1);assert.equal(searchTx(tx,'40000').length,1);assert.equal(searchTx(tx,'').length,3)});
