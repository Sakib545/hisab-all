// Calculations for the BURAQ bot data on the site — ported 1:1 from the bots' Python so numbers match.
export type Rec<D = Record<string, any>> = { bot: string; id: string; t: string; a: number | null; s: string; at: string; d: D; r?: string };
export type OrderData = { c: string; m: string; ph: string; p: string; desc: string; cod: number; b: string; f: string; imp: string; cs: string; ccod: number | null; fee: number; payout: number; col: number; ra: string };
export type TxData = { tx_id: number; bank: string; account: string; receiver: string; reference: string; date: string; time: string; payment_code: string; payment_month: string; remarks: string; has_image: boolean };
export type CycleData = { month: string; started_at: string; completed_at: string; count: number; total: number };

export const dhakaToday = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Dhaka' }).format(new Date());
export const dhakaDay = (iso: string) => /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso : new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Dhaka' }).format(new Date(iso));
export const orderDay = (o: Rec<OrderData>) => o.at.slice(0, 10);            // order_date (stored as YYYY-MM-DD → T06:00Z)
export const r2 = (n: number) => Math.round(n * 100) / 100;

/** settlement.py → _summarize(): live join of Deliveries + Paid Invoice. */
export function settlement(orders: Rec<OrderData>[]) {
  const products = new Map<string, { product: string; delivered: number; returned: number; pending: number }>();
  let totalCod = 0, deliveredCod = 0, returnCod = 0, pendingCod = 0, delivered = 0, returned = 0, pending = 0, charge = 0, payout = 0, collected = 0;
  for (const o of orders) {
    const cod = o.d.cod || 0, product = o.d.p || 'Unknown Product';
    totalCod += cod;
    const p = products.get(product) ?? { product, delivered: 0, returned: 0, pending: 0 };
    if (o.s === 'RETURNED') { returned++; returnCod += cod; p.returned++; }
    else if (o.s === 'DELIVERED') { delivered++; deliveredCod += cod; p.delivered++; }
    else { pending++; pendingCod += cod; p.pending++; }
    products.set(product, p);
    charge += o.d.fee || 0; payout += o.d.payout || 0; collected += o.d.col || 0;
  }
  const expected = r2(totalCod - returnCod - charge);
  return {
    total_parcels: orders.length, total_cod: r2(totalCod), delivered_parcels: delivered, delivered_cod: r2(deliveredCod),
    return_parcels: returned, return_cod: r2(returnCod), pending_parcels: pending, pending_cod: r2(pendingCod),
    total_charge: r2(charge), expected_settlement: expected, matched_payout: r2(payout), matched_collected: r2(collected),
    remaining: r2(expected - payout),
    products: [...products.values()].sort((a, b) => a.product.toLowerCase().localeCompare(b.product.toLowerCase())),
  };
}

/** database.py → courier_summary(): Return CSV / courier status view. */
export function courierSummary(orders: Rec<OrderData>[]) {
  let totalCod = 0, retN = 0, retCod = 0, delN = 0, delCod = 0, active = 0;
  const prod = new Map<string, { product: string; return_parcels: number; return_cod: number }>();
  for (const o of orders) {
    const cod = o.d.cod || 0, cs = (o.d.cs || 'UNKNOWN').toUpperCase(), eff = o.d.ccod ?? cod;
    totalCod += cod;
    if (cs === 'RETURNED') { retN++; retCod += eff; const p = prod.get(o.d.p) ?? { product: o.d.p, return_parcels: 0, return_cod: 0 }; p.return_parcels++; p.return_cod += eff; prod.set(o.d.p, p); }
    if (cs === 'DELIVERED') { delN++; delCod += eff; }
    if (['PENDING', 'IN_TRANSIT', 'UNKNOWN'].includes(cs)) active++;
  }
  return { total_parcels: orders.length, total_cod: r2(totalCod), return_parcels: retN, return_cod: r2(retCod), net_parcels: orders.length - retN,
    net_cod: r2(totalCod - retCod), delivered_parcels: delN, delivered_cod: r2(delCod), active_parcels: active,
    products: [...prod.values()].sort((a, b) => b.return_parcels - a.return_parcels || a.product.localeCompare(b.product)) };
}

/** Orders + COD per product for a date range (bot's Reports / Dashboard). */
export function productReport(orders: Rec<OrderData>[], from = '0000', to = '9999') {
  const m = new Map<string, { product: string; orders: number; cod: number }>();
  let n = 0, cod = 0;
  for (const o of orders) {
    const d = orderDay(o);
    if (d < from || d > to) continue;
    n++; cod += o.d.cod || 0;
    const p = m.get(o.d.p) ?? { product: o.d.p, orders: 0, cod: 0 };
    p.orders++; p.cod += o.d.cod || 0; m.set(o.d.p, p);
  }
  return { orders: n, cod: r2(cod), products: [...m.values()].sort((a, b) => b.orders - a.orders || a.product.localeCompare(b.product)) };
}

export const months = (dates: string[]) => [...new Set(dates.map(d => d.slice(0, 7)).filter(m => /^\d{4}-\d{2}$/.test(m)))].sort().reverse();

/** database.py → analytics_summary() for BankTrackerBot. */
export function bankAnalytics(txs: Rec<TxData>[], cycleCount: number) {
  const total = txs.reduce((s, t) => s + (t.a ?? 0), 0);
  const group = (key: (t: Rec<TxData>) => string) => {
    const g = new Map<string, { key: string; n: number; total: number }>();
    for (const t of txs) { const k = key(t); if (!k) continue; const x = g.get(k) ?? { key: k, n: 0, total: 0 }; x.n++; x.total += t.a ?? 0; g.set(k, x); }
    return [...g.values()].sort((a, b) => b.total - a.total);
  };
  return { n: txs.length, total, avg: txs.length ? total / txs.length : 0, cycles: cycleCount,
    top: group(t => (t.d.account || '').trim()).slice(0, 5), banks: group(t => t.d.bank || 'Unknown'),
    byMonth: group(t => t.d.payment_month || (t.d.date || '').slice(0, 7)).sort((a, b) => a.key.localeCompare(b.key)) };
}

/** BankTrackerBot /search: account, reference, date, amount, payment code. */
export function searchTx(txs: Rec<TxData>[], q: string) {
  const s = q.trim().toLowerCase();
  if (!s) return txs;
  return txs.filter(t => [t.d.account, t.d.reference, t.d.date, t.d.payment_code, t.d.receiver, t.d.bank, String((t.a ?? 0) / 100)].some(v => String(v ?? '').toLowerCase().includes(s)));
}
