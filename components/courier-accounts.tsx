'use client';
import {useState,useMemo} from 'react';
import {Search,Download,FileText,Send,Trash2,Package,RefreshCw} from 'lucide-react';
import {useBotData,useCommands,CommandLog,FileDrop,Tabs,Stats,downloadCsv,printReport,Confirm,EmptyBot,Notice,tkf,num,fmtDT,fmtDate,monthLabel,type Cmd} from './bot-kit';
import {settlement,courierSummary,productReport,months as monthsOf,dhakaToday,orderDay,type Rec,type OrderData} from '../lib/buraq';

const LABELS:Record<string,string>={upload:'File upload',delete_import:'Import delete',delete_invoice:'Paid Invoice delete',delete_all_invoices:'সব Paid Invoice delete',clear_duplicates:'Duplicate history clear',send_files:'Product Excel → Telegram',central_export:'Central Export → Telegram',resync:'পুরো data আবার sync'};
function describe(c:Cmd){const r=c.result||{};switch(c.action){
  case 'upload':
    if(r.type==='deliveries')return <>নতুন <b>{r.inserted}</b> · duplicate {r.file_duplicates+r.db_duplicates} · invalid {r.invalid} · COD {tkf(r.added_cod)}{r.cod_mismatches?<> · ⚠️ COD mismatch {r.cod_mismatches}</>:null}{r.products?.length?<> — {r.products.map((p:any)=>`${p.product} ${p.count}`).join(', ')}</>:null}</>;
    if(r.type==='paid_invoice')return <>{r.invoice_code}{r.already_imported?' (আগেই import করা)':''} · Delivered {r.matched_delivery} · Return {r.matched_return} · Unmatched {r.unmatched} · Payout {tkf(r.total_payout)}{r.warning&&<> — ⚠️ {r.warning}</>}</>;
    if(r.type==='return_csv')return r.already_imported?'এই Return CSV আগেই import করা হয়েছে':<>Pending → RETURNED <b>{r.updated_pending_orders}</b> · আগেই return {r.skipped_already_returned} · pending নয় {r.skipped_not_pending} · order পাওয়া যায়নি {r.unmatched_pending_orders}</>;
    return 'হয়েছে';
  case 'delete_import':return `${r.orders}টি order · COD ${tkf(r.cod)} বাদ`;
  case 'delete_invoice':return `${r.invoice_code} · ${r.deleted_rows} row`;
  case 'delete_all_invoices':return `${r.deleted_imports}টি invoice · ${r.deleted_rows} row`;
  case 'clear_duplicates':return `${r.cleared}টি মুছে ফেলা হয়েছে`;
  case 'send_files':return `${r.files}টি file Telegram-এ`;
  default:return 'হয়েছে';}}

type Tab='dash'|'settle'|'orders'|'imports'|'invoices'|'dups'|'returns';
type Imp={total:number;inserted:number;duplicates:number;invalid:number;duplicate_cod:number;files:string[]};
type Inv={id:number;rows:number;delivery_rows:number;return_rows:number;insta_fee_rows:number;matched_delivery:number;matched_return:number;unmatched:number;ignored_other:number;matched_by_merchant:number;matched_by_consignment:number;invoice_date_from:string;invoice_date_to:string;total_fee:number;total_payout:number};
type Dup={c:string;m:string;ph:string;od:string;orig:string;file:string;b:string};
const STATUS_BN:Record<string,string>={DELIVERED:'Delivered',RETURNED:'Returned',PENDING:'Pending'};
const ORDER_HEAD=['Order date','Consignment','Merchant Order ID','Phone','Product','COD','Settlement status','Courier status','Fee','Payout','Description','Source file'];
const orderRow=(o:Rec<OrderData>)=>[orderDay(o),o.d.c,o.d.m,o.d.ph,o.d.p,o.d.cod,o.s,o.d.cs,o.d.fee,o.d.payout,o.d.desc,o.d.f];

export default function CourierAccounts({notify,goBots}:{notify:(s:string)=>void;goBots:()=>void}){
  const {recs,loading,error,reload,bot,botInfo}=useBotData(['order','import','invoice','duplicate','return_import']);
  const cmd=useCommands(bot,reload);
  const [tab,setTab]=useState<Tab>('dash'),[q,setQ]=useState(''),[prod,setProd]=useState(''),[st,setSt]=useState(''),[mon,setMon]=useState(''),[period,setPeriod]=useState('today'),[day,setDay]=useState(dhakaToday()),[pmonth,setPmonth]=useState(dhakaToday().slice(0,7)),[smonth,setSmonth]=useState(''),[confirm,setConfirm]=useState(''),[err,setErr]=useState('');
  const orders=(recs.order??[]) as Rec<OrderData>[];
  const imports=(recs.import??[]) as Rec<Imp>[];
  const invoices=(recs.invoice??[]) as Rec<Inv>[];
  const dups=(recs.duplicate??[]) as Rec<Dup>[];
  const retImports=(recs.return_import??[]) as Rec<{total:number;returns:number;paid_returns:number}>[];
  const today=dhakaToday(), yest=new Date(Date.parse(today+'T00:00:00Z')-864e5).toISOString().slice(0,10);
  const allMonths=useMemo(()=>monthsOf(orders.map(orderDay)),[orders]);
  const products=useMemo(()=>[...new Set(orders.map(o=>o.d.p))].sort(),[orders]);

  async function go(action:string,payload:Record<string,any>={},file?:File){setErr('');try{await cmd.run(action,payload,file);return true}catch(e){setErr(String(e).replace(/^Error: /,''));return false}}
  const upload=(type:string)=>async(files:File[])=>{for(const f of files){if(!/\.(csv|xlsx|xls)$/i.test(f.name)){setErr(`${f.name}: শুধু .csv / .xlsx / .xls`);continue}if(await go('upload',{type},f))notify(`${f.name} bot-এ পাঠানো হয়েছে`)}};

  if(loading)return <div className="bh-loading">Loading…</div>;
  if(!bot)return <><div className="title-row"><div><h1>Courier & COD</h1><p className="subtitle">Smart Product Accounts Bot</p></div></div>{error?<Notice kind="error">{error}</Notice>:<EmptyBot name="Smart Product Accounts Bot" hint="Bot connect করে nexa patch বসালে সব parcel, settlement, Paid Invoice, import ও duplicate history এখানে আসবে — আর এখান থেকেই Deliveries / Paid Invoice / Return CSV upload করা যাবে।" onGo={goBots}/>}</>;

  // reports (bot's 📈 Reports menu)
  const [from,to,plabel]=period==='today'?[today,today,'আজ']:period==='yesterday'?[yest,yest,'গতকাল']:period==='month'?[today.slice(0,7)+'-01',today.slice(0,7)+'-31','চলতি মাস']:period==='day'?[day,day,fmtDate(day)]:period==='pmonth'?[pmonth+'-01',pmonth+'-31',monthLabel(pmonth)]:['0000','9999','সর্বমোট'];
  const rep=productReport(prod?orders.filter(o=>o.d.p===prod):orders,from,to);
  const totalRep=productReport(orders), monthRep=productReport(orders,today.slice(0,7)+'-01',today.slice(0,7)+'-31'), todayRep=productReport(orders,today,today);

  const sOrders=smonth?orders.filter(o=>orderDay(o).slice(0,7)===smonth):orders;
  const S=settlement(sOrders);
  const perMonth=allMonths.map(m=>({m,s:settlement(orders.filter(o=>orderDay(o).slice(0,7)===m))}));
  const R=courierSummary(orders);

  const sq=q.trim().toLowerCase();
  const shownOrders=orders.filter(o=>(!sq||[o.d.c,o.d.m,o.d.ph].some(v=>v?.toLowerCase().includes(sq)))&&(!prod||o.d.p===prod)&&(!st||o.s===st||o.d.cs===st)&&(!mon||orderDay(o).slice(0,7)===mon));
  const dupToday=dups.filter(d=>d.at.slice(0,10)===today).length, dupMonth=dups.filter(d=>d.at.slice(0,7)===today.slice(0,7)).length;

  const OrdersTable=({rows}:{rows:Rec<OrderData>[]})=>!rows.length?<p className="xb-none">কোনো order নেই।</p>:<div className="bh-table-wrap"><table className="bh-table"><thead><tr><th>তারিখ</th><th>Consignment / Order ID</th><th>Product</th><th>অবস্থা</th><th className="r">COD</th><th className="r">Fee / Payout</th></tr></thead><tbody>
    {rows.map(o=><tr key={o.id} className="static"><td className="t">{orderDay(o).split('-').reverse().join('/')}</td>
      <td className="title"><b className="mono">{o.d.c||'—'}</b><small>{o.d.m}{o.d.ph&&` · ${o.d.ph}`}</small></td>
      <td className="bot"><span className="badge">{o.d.p}</span>{o.d.desc&&<small className="bk-sub ell" title={o.d.desc}>{o.d.desc}</small>}</td>
      <td className="type"><span className={`bk-pill s-${o.s.toLowerCase()}`}>{STATUS_BN[o.s]??o.s}</span>{o.d.cs==='RETURNED'&&o.s!=='RETURNED'&&<span className="bk-pill s-returned" title="Return CSV">Return CSV</span>}</td>
      <td className="r amt">{tkf(o.d.cod)}</td><td className="r fee">{o.d.fee||o.d.payout?<>{tkf(o.d.fee)} / {tkf(o.d.payout)}</>:'—'}</td></tr>)}
  </tbody></table></div>;

  return <div className="bh bk">
    <div className="title-row"><div><h1>Courier & COD</h1><p className="subtitle">Smart Product Accounts · {botInfo?.label??bot} · শেষ sync {fmtDT(botInfo?.lastSeenAt??'')}</p></div>
      <div className="bh-head-actions"><button className="secondary" onClick={()=>{go('central_export');notify('Central Export Telegram-এ পাঠানো হচ্ছে')}}><Package size={16}/>Central Export</button><button className="secondary" onClick={()=>downloadCsv('Smart-Product-All-Orders',ORDER_HEAD,orders.map(orderRow))}><Download size={16}/>Full Export</button></div></div>
    {err&&<Notice kind="error" onClose={()=>setErr('')}>{err}</Notice>}
    <Tabs<Tab> value={tab} onChange={setTab} tabs={[['dash','Dashboard'],['settle','Settlement'],['orders','Orders',orders.length],['imports','Imports',imports.length],['invoices','Paid Invoice',invoices.length],['dups','Duplicates',dups.length],['returns','Returns',R.return_parcels]]}/>

    {tab==='dash'&&<>
      <div className="bk-uploads">
        <FileDrop accept=".csv,.xlsx,.xls" label="Deliveries CSV / Excel" hint="Pathao export। Product শনাক্ত, duplicate বাদ, COD হিসাব — Hair Oil 100ml ও Pain Oil-এর Excel Telegram-এ আসবে।" multiple onFiles={upload('deliveries')}/>
        <FileDrop accept=".csv,.xlsx,.xls" label="Paid Invoice CSV" hint="Merchant Order ID / Consignment ID দিয়ে Delivered ও Return মিলায়; fee ও payout বসায়। একই file আবার দিলে duplicate হয় না।" onFiles={upload('paid_invoice')}/>
        <FileDrop accept=".csv,.xlsx,.xls" label="Return CSV" hint="শুধু Pending order-কে RETURNED করে। Deliveries file এখানে দেবেন না।" onFiles={upload('return_csv')}/>
      </div>
      <Stats items={[['আজ',num(todayRep.orders)+' অর্ডার',tkf(todayRep.cod)],['চলতি মাস',num(monthRep.orders)+' অর্ডার',tkf(monthRep.cod)],['সর্বমোট',num(totalRep.orders)+' অর্ডার',tkf(totalRep.cod)],['Settlement বাকি',tkf(settlement(orders).remaining),`Payout ${tkf(settlement(orders).matched_payout)}`]]}/>
      <section className="panel bk-rep">
        <div className="bk-rep-head"><h3>রিপোর্ট</h3>
          <div className="xb-periods">{[['today','আজ'],['yesterday','গতকাল'],['month','চলতি মাস'],['all','সর্বমোট']].map(([k,l])=><button key={k} className={period===k?'on':''} onClick={()=>setPeriod(k)}>{l}</button>)}
            <input type="date" value={day} onChange={e=>{setDay(e.target.value);setPeriod('day')}} className={period==='day'?'on':''} aria-label="নির্দিষ্ট তারিখ"/>
            <input type="month" value={pmonth} onChange={e=>{setPmonth(e.target.value);setPeriod('pmonth')}} className={period==='pmonth'?'on':''} aria-label="নির্দিষ্ট মাস"/>
            <select value={prod} onChange={e=>setProd(e.target.value)} aria-label="Product"><option value="">সব product</option>{products.map(p=><option key={p}>{p}</option>)}</select></div></div>
        <div className="xb-total"><span>{plabel}{prod&&` · ${prod}`}</span><b>{num(rep.orders)} অর্ডার · {tkf(rep.cod)}</b></div>
        {rep.products.length>0&&<ul className="bk-bars">{rep.products.map(p=><li key={p.product}><div><span>{p.product}</span><b>{num(p.orders)} · {tkf(p.cod)}</b></div><i style={{width:`${p.orders/rep.products[0].orders*100}%`}}/></li>)}</ul>}
      </section>
    </>}

    {tab==='settle'&&<>
      <div className="xb-periods"><button className={!smonth?'on':''} onClick={()=>setSmonth('')}>সব মাস</button>{allMonths.map(m=><button key={m} className={smonth===m?'on':''} onClick={()=>setSmonth(m)}>{monthLabel(m)}</button>)}</div>
      <section className="panel bk-settle">
        <h2>📊 Settlement — {smonth?monthLabel(smonth):'সব মাস'}</h2>
        <dl>{([['মোট Parcel',num(S.total_parcels)],['মোট COD',tkf(S.total_cod)],['✅ Delivered',`${num(S.delivered_parcels)} · ${tkf(S.delivered_cod)}`],['↩️ Returned',`${num(S.return_parcels)} · ${tkf(S.return_cod)}`],['⏳ Pending',`${num(S.pending_parcels)} · ${tkf(S.pending_cod)}`],['Courier charge',tkf(S.total_charge)],['Expected settlement',tkf(S.expected_settlement)],['Paid Invoice payout',tkf(S.matched_payout)],['Collected',tkf(S.matched_collected)]] as [string,string][]).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
          <div className="hl"><dt>Remaining</dt><dd>{tkf(S.remaining)}</dd></div></dl>
        <h3 className="bk-h">Product-wise</h3>
        <table className="bh-table"><thead><tr><th>Product</th><th className="r">Delivered</th><th className="r">Returned</th><th className="r">Pending</th></tr></thead><tbody>{S.products.map(p=><tr key={p.product} className="static"><td className="title"><b>{p.product}</b></td><td className="r">{p.delivered}</td><td className="r">{p.returned}</td><td className="r">{p.pending}</td></tr>)}</tbody></table>
        <p className="bk-note">হিসাব bot-এর মতোই: Deliveries + Paid Invoice live join (Merchant Order ID, তারপর Consignment ID)। Expected = COD − Return COD − Charge; Remaining = Expected − Payout।</p>
      </section>
      <section className="panel xb-list"><div className="bk-sec-head"><h3>মাসভিত্তিক হিসাব (Courier Monthly)</h3><div className="bk-actions">
        <button className="secondary" onClick={()=>downloadCsv('Courier-Monthly',['Month','Total Parcel','Total COD','Delivered','Delivered COD','Returned','Return COD','Pending','Pending COD','Courier Charge','Expected Settlement','Paid Invoice Payout','Collected','Remaining'],perMonth.map(({m,s})=>[m,s.total_parcels,s.total_cod,s.delivered_parcels,s.delivered_cod,s.return_parcels,s.return_cod,s.pending_parcels,s.pending_cod,s.total_charge,s.expected_settlement,s.matched_payout,s.matched_collected,s.remaining]))}><Download size={15}/>CSV</button>
        <button className="secondary" onClick={()=>printReport('Courier Monthly Settlement','Smart Product Accounts',[{headers:['মাস','Parcel','COD','Delivered','Returned','Pending','Charge','Expected','Payout','Remaining'],right:[1,2,3,4,5,6,7,8,9],rows:perMonth.map(({m,s})=>[monthLabel(m),s.total_parcels,tkf(s.total_cod),s.delivered_parcels,s.return_parcels,s.pending_parcels,tkf(s.total_charge),tkf(s.expected_settlement),tkf(s.matched_payout),tkf(s.remaining)])}])}><FileText size={15}/>PDF</button></div></div>
        <div className="bh-table-wrap"><table className="bh-table"><thead><tr><th>মাস</th><th className="r">Parcel</th><th className="r">COD</th><th className="r">Delivered</th><th className="r">Returned</th><th className="r">Pending</th><th className="r">Charge</th><th className="r">Expected</th><th className="r">Payout</th><th className="r">Remaining</th></tr></thead><tbody>
          {perMonth.map(({m,s})=><tr key={m} tabIndex={0} onClick={()=>setSmonth(m)}><td className="title"><b>{monthLabel(m)}</b></td><td className="r">{s.total_parcels}</td><td className="r">{tkf(s.total_cod)}</td><td className="r">{s.delivered_parcels}</td><td className="r">{s.return_parcels}</td><td className="r">{s.pending_parcels}</td><td className="r">{tkf(s.total_charge)}</td><td className="r">{tkf(s.expected_settlement)}</td><td className="r">{tkf(s.matched_payout)}</td><td className="r amt">{tkf(s.remaining)}</td></tr>)}
        </tbody></table></div></section>
    </>}

    {tab==='orders'&&<>
      <div className="bh-filters panel bk-filterbar"><div className="bh-search"><Search size={15}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Consignment ID, Merchant Order ID বা phone…" aria-label="Find order"/></div>
        <select value={prod} onChange={e=>setProd(e.target.value)} aria-label="Product"><option value="">সব product</option>{products.map(p=><option key={p}>{p}</option>)}</select>
        <select value={st} onChange={e=>setSt(e.target.value)} aria-label="Status"><option value="">সব অবস্থা</option><option value="DELIVERED">Delivered</option><option value="RETURNED">Returned</option><option value="PENDING">Pending</option></select>
        <select value={mon} onChange={e=>setMon(e.target.value)} aria-label="মাস"><option value="">সব মাস</option>{allMonths.map(m=><option key={m} value={m}>{monthLabel(m)}</option>)}</select>
        <button className="secondary" onClick={()=>downloadCsv('orders',ORDER_HEAD,shownOrders.map(orderRow))}><Download size={15}/>CSV</button></div>
      <p className="bk-count">{num(shownOrders.length)}টি order · COD {tkf(shownOrders.reduce((s,o)=>s+(o.d.cod||0),0))}</p>
      <section className="panel xb-list"><OrdersTable rows={shownOrders.slice(0,300)}/>{shownOrders.length>300&&<p className="xb-none">প্রথম ৩০০টি দেখানো হচ্ছে — খুঁজে ছোট করুন বা CSV নিন।</p>}</section>
    </>}

    {tab==='imports'&&<section className="panel xb-list">{!imports.length?<p className="xb-none">এখনো কোনো Deliveries import নেই।</p>:<div className="bh-table-wrap"><table className="bh-table"><thead><tr><th>সময়</th><th>File</th><th className="r">Row</th><th className="r">নতুন</th><th className="r">Duplicate</th><th className="r">COD যোগ</th><th aria-label="actions"/></tr></thead><tbody>
      {imports.map(i=><tr key={i.id} className="static"><td className="t">{fmtDT(i.at)}</td><td className="title"><b>{i.t}</b>{i.d.files?.length>0&&<small>{i.d.files.length}টি Excel file</small>}</td><td className="r">{i.d.total}</td><td className="r">{i.d.inserted}</td><td className="r">{i.d.duplicates}{i.d.invalid?` · ${i.d.invalid} invalid`:''}</td><td className="r amt">{tkf((i.a??0)/100)}</td>
        <td className="xb-act">{confirm===i.id?<span className="xb-confirm"><small>{i.d.inserted}টি order, COD আর history মুছে যাবে</small><button className="danger solid" onClick={()=>{go('delete_import',{batch_id:i.id});setConfirm('')}}>Delete</button><button className="secondary" onClick={()=>setConfirm('')}>না</button></span>:<>
          {i.d.files?.length>0&&<button className="bh-gear static" title="Product Excel Telegram-এ" aria-label="Files to Telegram" onClick={()=>{go('send_files',{batch_id:i.id});notify('File গুলো Telegram-এ পাঠানো হচ্ছে')}}><Send size={15}/></button>}
          <button className="bh-gear static" aria-label={`Delete import ${i.t}`} onClick={()=>setConfirm(i.id)}><Trash2 size={15}/></button></>}</td></tr>)}
    </tbody></table></div>}</section>}

    {tab==='invoices'&&<>
      {invoices.length>0&&<div className="bk-actions right">{confirm==='allinv'?<Confirm danger text="সব Paid Invoice মুছে যাবে। Deliveries data থাকবে; সব order আবার Pending হবে।" yes="সব delete" onYes={()=>{go('delete_all_invoices');setConfirm('')}} onNo={()=>setConfirm('')}/>:<button className="danger" onClick={()=>setConfirm('allinv')}><Trash2 size={15}/>সব Paid Invoice delete</button>}</div>}
      <section className="panel xb-list">{!invoices.length?<p className="xb-none">এখনো কোনো Paid Invoice নেই।</p>:<div className="bh-table-wrap"><table className="bh-table"><thead><tr><th>Invoice</th><th>সময়কাল</th><th className="r">Row</th><th className="r">Delivered</th><th className="r">Return</th><th className="r">Unmatched / Other</th><th className="r">Fee</th><th className="r">Payout</th><th aria-label="actions"/></tr></thead><tbody>
        {invoices.map(v=><tr key={v.id} className="static"><td className="title"><b>{v.id}</b><small>{v.t} · {fmtDT(v.at)}</small></td><td className="t">{v.d.invoice_date_from?`${v.d.invoice_date_from} – ${v.d.invoice_date_to}`:'—'}</td><td className="r">{v.d.rows}</td><td className="r">{v.d.matched_delivery}</td><td className="r">{v.d.matched_return}</td><td className="r">{v.d.unmatched} / {v.d.ignored_other}</td><td className="r">{tkf(v.d.total_fee)}</td><td className="r amt">{tkf(v.d.total_payout)}</td>
          <td className="xb-act">{confirm===v.id?<span className="xb-confirm"><button className="danger solid" onClick={()=>{go('delete_invoice',{import_id:v.d.id});setConfirm('')}}>Delete</button><button className="secondary" onClick={()=>setConfirm('')}>না</button></span>:<button className="bh-gear static" aria-label={`Delete ${v.id}`} onClick={()=>setConfirm(v.id)}><Trash2 size={15}/></button>}</td></tr>)}
      </tbody></table></div>}
      {invoices.some(v=>v.d.rows>0&&!v.d.matched_delivery&&!v.d.matched_return)&&<Notice kind="warn">কোনো invoice-এ একটিও order match হয়নি — সম্ভবত সেই সময়ের Deliveries CSV আগে upload করা হয়নি।</Notice>}</section></>}

    {tab==='dups'&&<>
      <Stats items={[['মোট duplicate',num(dups.length)],['আজ',num(dupToday)],['এই মাস',num(dupMonth)],['Duplicate COD',tkf(dups.reduce((s,d)=>s+(d.a??0)/100,0))]]}/>
      <div className="bk-actions right"><button className="secondary" onClick={()=>downloadCsv('duplicates',['Time','Reason','Consignment','Merchant Order ID','Phone','Product','COD','Order date','Original file','Duplicate file'],dups.map(d=>[d.at,d.s,d.d.c,d.d.m,d.d.ph,d.t,(d.a??0)/100,d.d.od,d.d.orig,d.d.file]))}><Download size={15}/>CSV</button>
        {confirm==='dupclear'?<Confirm danger text="Duplicate history মুছে যাবে (order-এ কোনো প্রভাব নেই)।" yes="Clear" onYes={()=>{go('clear_duplicates');setConfirm('')}} onNo={()=>setConfirm('')}/>:dups.length>0&&<button className="danger" onClick={()=>setConfirm('dupclear')}><Trash2 size={15}/>Clear</button>}</div>
      <section className="panel xb-list">{!dups.length?<p className="xb-none">কোনো duplicate নেই।</p>:<div className="bh-table-wrap"><table className="bh-table"><thead><tr><th>সময়</th><th>কারণ</th><th>Consignment / Order ID</th><th>Product</th><th>File</th><th className="r">COD</th></tr></thead><tbody>
        {dups.slice(0,300).map(d=><tr key={d.id} className="static"><td className="t">{fmtDT(d.at)}</td><td className="type"><span className="badge">{d.s}</span></td><td className="title"><b className="mono">{d.d.c||'—'}</b><small>{d.d.m}</small></td><td className="bot">{d.t}</td><td className="t">{d.d.file}{d.d.orig&&<small className="bk-sub">আগে: {d.d.orig}</small>}</td><td className="r amt">{tkf((d.a??0)/100)}</td></tr>)}
      </tbody></table></div>}</section></>}

    {tab==='returns'&&<>
      <Stats items={[['Return parcel',num(R.return_parcels),tkf(R.return_cod)],['Net parcel',num(R.net_parcels),`Net COD ${tkf(R.net_cod)}`],['Delivered',num(R.delivered_parcels),tkf(R.delivered_cod)],['Pending / in transit',num(R.active_parcels)]]}/>
      <div className="xb-grid">
        <section className="panel xb-report"><h3 className="bk-h">Product-wise return</h3>{!R.products.length?<p className="xb-none">কোনো return নেই।</p>:<ul>{R.products.map(p=><li key={p.product}><div><span>{p.product}</span><b>{p.return_parcels} · {tkf(p.return_cod)}</b></div><i style={{width:`${p.return_parcels/R.products[0].return_parcels*100}%`}}/></li>)}</ul>}
          <h3 className="bk-h">Return CSV imports</h3>{!retImports.length?<p className="xb-none">নেই।</p>:<ul className="bk-plain">{retImports.map(r=><li key={r.id}><b>{r.t}</b><small>{fmtDT(r.at)} · {r.d.returns} return ({r.d.paid_returns} paid) / {r.d.total} row</small></li>)}</ul>}</section>
        <section className="panel xb-list"><OrdersTable rows={orders.filter(o=>o.d.cs==='RETURNED').slice(0,200)}/></section>
      </div>
      <p className="bk-note">এই page Return CSV / courier status অনুযায়ী (bot-এর ↩️ Return Report)। Settlement-এর Returned সংখ্যা Paid Invoice থেকে আসে, তাই দুটো আলাদা হতে পারে।</p>
    </>}

    <div className="bk-actions right bk-foot"><button className="link" onClick={()=>{go('resync');notify('Bot পুরো data আবার পাঠাবে')}}><RefreshCw size={13}/>পুরো data আবার sync</button></div>
    <CommandLog list={cmd.list} labels={LABELS} describe={describe} cancel={cmd.cancel} lastSeen={botInfo?.lastSeenAt}/>
  </div>;
}
