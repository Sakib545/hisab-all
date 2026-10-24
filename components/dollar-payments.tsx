'use client';
import {useState,useMemo} from 'react';
import {Search,Download,FileText,Send,Image as ImageIcon,Trash2,CheckCircle2,RotateCcw,CalendarDays,Stethoscope,Wrench,Archive,RefreshCw,ArrowLeft,PenLine,X} from 'lucide-react';
import {useBotData,useCommands,CommandLog,FileDrop,Tabs,Stats,downloadCsv,printReport,Confirm,EmptyBot,Notice,tk,num,fmtDT,fmtDate,monthLabel,type Cmd} from './bot-kit';
import {bankAnalytics,searchTx,dhakaToday,type Rec,type TxData,type CycleData} from '../lib/buraq';

const LABELS:Record<string,string>={add_receipt:'Receipt যোগ',add_manual:'হাতে লেখা entry',complete_payment:'Complete Payment',reopen_payment:'Payment Reopen',set_month:'মাস বদল',delete_tx:'Receipt delete',send_excel:'Excel → Telegram',send_pdf:'PDF → Telegram',send_receipt:'Receipt ছবি → Telegram',doctor:'System Doctor',maintenance:'Maintenance',backup:'Full backup → Telegram',resync:'পুরো data আবার sync'};
function describe(c:Cmd){const r=c.result||{};switch(c.action){
  case 'add_manual':return r.saved?`#${r.tx_id} · ${r.bank_name} · ${r.account} · ৳${Number(r.amount).toLocaleString('en-BD')} · ${r.date}${r.with_image?' · ছবিসহ':''}`:'এই ছবি আগেই save করা — duplicate যোগ হয়নি';
  case 'add_receipt':if(r.reason==='needs_details')return r.slip?'Cash deposit slip — হাতে লেখা amount পড়া যায়নি, উপরে amount লিখুন':'পুরো পড়া যায়নি — উপরে amount লিখে save করুন';
    return r.saved?`#${r.tx_id} · ${r.bank_name} → ${r.account_number} · ৳${Number(r.amount).toLocaleString('en-BD')} · ${r.payment_code}`:r.reason==='duplicate'?'আগেই save করা — duplicate যোগ হয়নি':`পড়া যায়নি: ${(r.missing||[]).join(', ')}`;
  case 'complete_payment':return `${r.completed} lock · ${r.count}টি receipt · ৳${Number(r.total).toLocaleString('en-BD')} → নতুন ${r.new_code}`;
  case 'reopen_payment':return `${r.active} এখন Running`;
  case 'set_month':return `${r.code} → ${monthLabel(r.month)}`;
  case 'delete_tx':return `#${r.deleted} মুছে ফেলা হয়েছে`;
  case 'doctor':return `Health ${r.score}%`;
  case 'maintenance':return `সফল ${r.success} · ব্যর্থ ${r.failed}`;
  case 'backup':return `${r.file} (${r.size_mb} MB) Telegram-এ পাঠানো হয়েছে`;
  case 'send_excel':case 'send_pdf':return `${r.rows}টি receipt Telegram-এ পাঠানো হয়েছে`;
  default:return 'হয়েছে';}}

const BANKS=['IFIC','PUBALI','CASH','bKash','Nagad','Rocket','DBBL','BRAC','Islami','Sonali'];
type Manual={amount:string;date:string;account:string;bank:string;note:string};

function ManualForm({init,today,title,sub,onSubmit,onClose,busy}:{init?:Partial<Manual>;today:string;title:string;sub?:React.ReactNode;onSubmit:(m:Manual)=>Promise<boolean>;onClose?:()=>void;busy?:boolean}){
  const [m,setM]=useState<Manual>({amount:'',date:today,account:'',bank:'',note:'',...init});
  const [err,setErr]=useState('');
  const amt=Number(m.amount.replace(/[,\s৳]/g,'').replace(/[০-৯]/g,d=>String('০১২৩৪৫৬৭৮৯'.indexOf(d))));
  const set=(k:keyof Manual)=>(e:{target:{value:string}})=>{setM({...m,[k]:e.target.value});setErr('')};
  async function submit(){
    if(!(amt>0))return setErr('Amount লিখুন।');
    if(m.date>today)return setErr('তারিখ ভবিষ্যতের হতে পারে না।');
    if(m.account&&!/^[\d\s-]{6,}$/.test(m.account))return setErr('Account নম্বর শুধু সংখ্যা (৬+ digit)।');
    if(await onSubmit({...m,amount:String(amt),account:m.account.replace(/\D/g,'')}))setM({amount:'',date:today,account:'',bank:'',note:''});
  }
  return <section className="panel bk-manual">
    <div className="bk-manual-head"><div><h3><PenLine size={15}/>{title}</h3>{sub&&<p>{sub}</p>}</div>{onClose&&<button className="bh-icon" onClick={onClose} aria-label="বন্ধ"><X size={15}/></button>}</div>
    <div className="bk-manual-grid">
      <label className="bh-field big">Amount (৳)*<input inputMode="decimal" autoFocus value={m.amount} onChange={set('amount')} placeholder="100000" onKeyDown={e=>{if(e.key==='Enter')submit()}}/></label>
      <label className="bh-field">তারিখ<input type="date" max={today} value={m.date} onChange={set('date')}/></label>
      <label className="bh-field">Account নম্বর<input inputMode="numeric" value={m.account} onChange={set('account')} placeholder="ঐচ্ছিক"/></label>
      <label className="bh-field">Bank<select value={m.bank} onChange={set('bank')}><option value="">—</option>{BANKS.map(b=><option key={b}>{b}</option>)}</select></label>
      <label className="bh-field wide">নাম / নোট<input value={m.note} onChange={set('note')} placeholder="ঐচ্ছিক — যেমন Depositor-এর নাম" maxLength={200}/></label>
    </div>
    {amt>0&&<p className="bk-manual-preview">Running payment-এ যোগ হবে: <b>৳{amt.toLocaleString('en-BD')}</b> · {m.date.split('-').reverse().join('/')}{m.account&&` · ${m.account}`}{m.bank&&` · ${m.bank}`}</p>}
    {err&&<p className="bh-error" role="alert">{err}</p>}
    <div className="bh-actions left"><button className="primary" disabled={busy} onClick={submit}>Save</button>{onClose&&<button className="secondary" onClick={onClose}>বাতিল</button>}</div>
  </section>;
}

type Tab='overview'|'payments'|'receipts'|'analytics'|'activity'|'tools';
const txRow=(t:Rec<TxData>)=>[t.d.tx_id,t.d.payment_code,t.d.date,t.d.time,t.d.bank,t.d.account,t.d.receiver||'',t.d.reference||'',((t.a??0)/100).toFixed(2)];
const TX_HEAD=['ID','Payment','Date','Time','Bank','Receiver Account','Receiver','Transaction ID','Amount'];

export default function DollarPayments({notify,goBots}:{notify:(s:string)=>void;goBots:()=>void}){
  const {recs,loading,error,reload,bot,botInfo}=useBotData(['cycle','bank_tx','activity']);
  const cmd=useCommands(bot,reload);
  const [tab,setTab]=useState<Tab>('overview'),[q,setQ]=useState(''),[range,setRange]=useState('all'),[open,setOpen]=useState(''),[confirm,setConfirm]=useState(''),[month,setMonth]=useState(''),[manual,setManual]=useState(false),[skipped,setSkipped]=useState<string[]>([]),[err,setErr]=useState('');
  const cycles=(recs.cycle??[]) as Rec<CycleData>[];
  const txs=useMemo(()=>((recs.bank_tx??[]) as Rec<TxData>[]).slice().sort((a,b)=>b.at.localeCompare(a.at)),[recs.bank_tx]);
  const activity=(recs.activity??[]) as Rec<{details:string}>[];
  const active=cycles.find(c=>c.s==='ACTIVE');
  const today=dhakaToday();
  const sorted=[...cycles].sort((a,b)=>Number(b.id.replace(/\D/g,''))-Number(a.id.replace(/\D/g,'')));
  const an=useMemo(()=>bankAnalytics(txs,cycles.length),[txs,cycles.length]);

  async function go(action:string,payload:Record<string,any>={},file?:File){setErr('');try{await cmd.run(action,payload,file);return true}catch(e){setErr(String(e).replace(/^Error: /,''));return false}}
  async function uploadReceipts(files:File[]){const imgs=files.filter(f=>/image\//.test(f.type)||/\.(jpe?g|png|webp)$/i.test(f.name));if(!imgs.length){setErr('শুধু receipt-এর ছবি (JPG/PNG) দিন।');return}
    let n=0;for(const f of imgs)if(await go('add_receipt',{},f))n++;if(n)notify(`${n}টি receipt bot-এ পাঠানো হয়েছে — পড়ে active payment-এ save করবে`)}

  const completed=new Set(cmd.list.filter(c=>c.action==='add_manual'&&c.status!=='failed').map(c=>c.payload?.pending_id));
  const needs=cmd.list.filter(c=>c.action==='add_receipt'&&c.status==='done'&&c.result?.reason==='needs_details'&&!completed.has(c.result.pending_id)&&!skipped.includes(c.id));
  const saveManual=async(m:Manual,extra:Record<string,any>={})=>{const ok=await go('add_manual',{...m,...extra});if(ok)notify('Bot-এ পাঠানো হয়েছে — Running payment-এ save হবে');return ok};

  if(loading)return <div className="bh-loading">Loading…</div>;
  if(!bot)return <><div className="title-row"><div><h1>Dollar payments</h1><p className="subtitle">BURAQ DOLLER PAYMENT — BankTrackerBot</p></div></div>{error?<Notice kind="error">{error}</Notice>:<EmptyBot name="BankTrackerBot" hint="Bot connect করে nexa patch বসালে Payment cycle, সব receipt, activity log এখানে আসবে — আর এখান থেকেই receipt upload, Complete Payment, Excel/PDF সব করা যাবে।" onGo={goBots}/>}</>;

  const range_=(t:Rec<TxData>)=>range==='all'||(range==='today'?t.d.date===today:t.d.date?.slice(0,7)===range);
  const shownTx=searchTx(txs,q).filter(range_);
  const txMonths=[...new Set(txs.map(t=>t.d.date?.slice(0,7)).filter(Boolean))].sort().reverse();
  const openCycle=sorted.find(c=>c.id===open);
  const cycleTx=open?txs.filter(t=>t.d.payment_code===open).sort((a,b)=>a.at.localeCompare(b.at)):[];

  const TxTable=({rows,withCycle=true}:{rows:Rec<TxData>[];withCycle?:boolean})=>!rows.length?<p className="xb-none">কোনো receipt নেই।</p>:
    <div className="bh-table-wrap"><table className="bh-table"><thead><tr><th>তারিখ</th>{withCycle&&<th>Payment</th>}<th>Receiver account</th><th>Bank</th><th>Transaction ID</th><th className="r">Amount</th><th aria-label="actions"/></tr></thead><tbody>
      {rows.map(t=><tr key={t.id} className="static">
        <td className="t">{t.d.date?.split('-').reverse().join('/')}<small className="bk-sub">{t.d.time}</small></td>
        {withCycle&&<td className="bot"><button className="bh-chip k-finance as-link" onClick={()=>{setOpen(t.d.payment_code);setTab('payments')}}>{t.d.payment_code}</button></td>}
        <td className="title"><b className="mono">{t.d.account}</b>{/^Cash deposit slip/.test(t.d.remarks||'')?<span className="bk-pill tag">Slip · হাতে লেখা</span>:/^Manual/.test(t.d.remarks||'')?<span className="bk-pill tag">Manual</span>:null}{t.d.receiver&&<small>{t.d.receiver}</small>}</td>
        <td className="type"><span className="badge">{t.d.bank}</span></td>
        <td className="mono small ref">{t.d.reference||'—'}</td>
        <td className="r amt">{tk(t.a)}</td>
        <td className="xb-act">{confirm===t.id?<span className="xb-confirm"><button className="danger solid" onClick={()=>{go('delete_tx',{tx_id:t.d.tx_id});setConfirm('')}}>Delete</button><button className="secondary" onClick={()=>setConfirm('')}>না</button></span>:<>
          {t.d.has_image&&<button className="bh-gear static" title="Receipt ছবি Telegram-এ দেখুন" aria-label={`Receipt #${t.d.tx_id} Telegram-এ পাঠাও`} onClick={()=>{go('send_receipt',{tx_id:t.d.tx_id});notify('Receipt ছবি Telegram-এ পাঠানো হচ্ছে')}}><ImageIcon size={15}/></button>}
          <button className="bh-gear static" aria-label={`Delete receipt #${t.d.tx_id}`} onClick={()=>setConfirm(t.id)}><Trash2 size={15}/></button></>}</td>
      </tr>)}</tbody></table></div>;

  const exportCycle=(code:string|null)=>{const rows=code?txs.filter(t=>t.d.payment_code===code).sort((a,b)=>a.at.localeCompare(b.at)):[...txs].reverse();return rows};

  return <div className="bh bk">
    <div className="title-row"><div><h1>Dollar payments</h1><p className="subtitle">BURAQ DOLLER PAYMENT · {botInfo?.label??bot} · শেষ sync {fmtDT(botInfo?.lastSeenAt??'')}</p></div>
      <div className="bh-head-actions"><button className="secondary" onClick={()=>{downloadCsv('BURAQ-Dollar-Payments-All',TX_HEAD,exportCycle(null).map(txRow))}}><Download size={16}/>সব Excel (CSV)</button></div></div>
    {err&&<Notice kind="error" onClose={()=>setErr('')}>{err}</Notice>}

    <Tabs<Tab> value={tab} onChange={t=>{setTab(t);setOpen('')}} tabs={[['overview','Dashboard'],['payments','Payments',cycles.length],['receipts','Receipts',txs.length],['analytics','Analytics'],['activity','Activity'],['tools','Tools']]}/>

    {tab==='overview'&&<>
      {needs.map(c=><ManualForm key={c.id} today={today} title={c.result.slip?`🧾 Cash deposit slip — ${c.result.file}`:`⚠️ পুরো পড়া যায়নি — ${c.result.file}`}
        sub={<>হাতে লেখা সংখ্যা ছবি থেকে নির্ভরযোগ্যভাবে পড়া যায় না। Slip দেখে amount লিখুন — ছবিটা receipt হিসেবে সাথে save হবে।</>}
        init={{date:c.result.hints?.date||today,account:c.result.hints?.account||'',bank:c.result.hints?.bank||(c.result.slip?'IFIC':'')}}
        onSubmit={m=>saveManual(m,{pending_id:c.result.pending_id,slip:!!c.result.slip})} onClose={()=>setSkipped(x=>[...x,c.id])}/>)}
      {manual&&<ManualForm today={today} title="হাতে লিখে যোগ (ছবি ছাড়া)" sub="Telegram-এও শুধু লিখে পাঠানো যায়: 1000 অথবা 100000 0220249853811 13/10/2026" onSubmit={async m=>{const ok=await saveManual(m);if(ok)setManual(false);return ok}} onClose={()=>setManual(false)}/>}
      <section className="panel bk-hero">
        <div className="bk-hero-main"><span className="bk-pill live">🟢 Running Payment</span><h2>{active?.id??'—'}</h2><p>{monthLabel(active?.d.month??'')} · {num(active?.d.count??0)}টি receipt</p><b className="bk-big">{tk(active?.a??0)}</b></div>
        <div className="bk-hero-side">
          <FileDrop accept="image/*" multiple label="Pubali / IFIC receipt বা deposit slip-এর ছবি দিন" hint="একসাথে অনেকগুলো দেওয়া যায়। Bot নিজের OCR দিয়ে পড়ে Running Payment-এ save করবে। হাতে লেখা slip হলে এখানেই amount লিখতে বলবে।" onFiles={uploadReceipts}/>
          {!manual&&<button className="secondary bk-wide" onClick={()=>setManual(true)}><PenLine size={16}/>হাতে লিখে যোগ (ছবি ছাড়া)</button>}
          {active&&(confirm==='complete'?<Confirm text={<>{active.id} lock হবে ({num(active.d.count)}টি receipt, {tk(active.a)}), নতুন Payment ID শুরু হবে।</>} yes="Complete করুন" onYes={()=>{go('complete_payment');setConfirm('')}} onNo={()=>setConfirm('')}/>
            :<button className="primary bk-wide" disabled={!active.d.count} onClick={()=>setConfirm('complete')}><CheckCircle2 size={16}/>Complete Payment</button>)}
        </div>
      </section>
      <Stats items={[['সব receipt',num(an.n),`${cycles.length}টি payment`],['মোট',tk(an.total),`গড় ${tk(an.avg)}`],['আজ',tk(txs.filter(t=>t.d.date===today).reduce((s,t)=>s+(t.a??0),0)),`${txs.filter(t=>t.d.date===today).length}টি receipt`],['এই মাস',tk(txs.filter(t=>t.d.date?.slice(0,7)===today.slice(0,7)).reduce((s,t)=>s+(t.a??0),0)),monthLabel(today.slice(0,7))]]}/>
      <section className="panel xb-list"><div className="bk-sec-head"><h3>সাম্প্রতিক receipt</h3><button className="link" onClick={()=>setTab('receipts')}>সব দেখুন</button></div><TxTable rows={txs.slice(0,8)}/></section>
    </>}

    {tab==='payments'&&!openCycle&&<section className="panel xb-list">
      <div className="bh-table-wrap"><table className="bh-table"><thead><tr><th>Payment</th><th>মাস</th><th>অবস্থা</th><th className="r">Receipts</th><th className="r">মোট</th><th>শুরু</th><th>শেষ</th></tr></thead><tbody>
        {sorted.map(c=><tr key={c.id} tabIndex={0} onClick={()=>setOpen(c.id)} onKeyDown={e=>{if(e.key==='Enter')setOpen(c.id)}}>
          <td className="title"><b>{c.id}</b></td><td className="type">{monthLabel(c.d.month)}</td>
          <td className="bot">{c.s==='ACTIVE'?<span className="bk-pill live">Running</span>:<span className="bk-pill">Completed</span>}</td>
          <td className="r">{num(c.d.count)}</td><td className="r amt">{tk(c.a)}</td><td className="t">{fmtDate(c.d.started_at)}</td><td className="t">{c.d.completed_at?fmtDate(c.d.completed_at):'—'}</td></tr>)}
      </tbody></table></div></section>}

    {tab==='payments'&&openCycle&&<>
      <button className="link bk-back" onClick={()=>setOpen('')}><ArrowLeft size={14}/>সব payment</button>
      <section className="panel bk-cycle">
        <div><h2>{openCycle.id} {openCycle.s==='ACTIVE'?<span className="bk-pill live">Running</span>:<span className="bk-pill">Completed</span>}</h2>
          <p>{monthLabel(openCycle.d.month)} · {num(openCycle.d.count)}টি receipt · <b>{tk(openCycle.a)}</b></p></div>
        <div className="bk-actions">
          <button className="secondary" onClick={()=>downloadCsv(`${openCycle.id}-Payment-Report`,TX_HEAD,cycleTx.map(txRow))}><Download size={15}/>CSV</button>
          <button className="secondary" onClick={()=>printReport(`BURAQ DOLLER PAYMENT — ${openCycle.id}`,`${monthLabel(openCycle.d.month)} · ${cycleTx.length} receipts`,[{headers:['SL','Date','Time','Receiver Account','Bank','Amount'],right:[5],rows:cycleTx.map((t,i)=>[i+1,t.d.date,t.d.time,t.d.account,t.d.bank,tk(t.a)]),foot:['','','','','মোট',tk(openCycle.a)]}])}><FileText size={15}/>PDF</button>
          <button className="secondary" onClick={()=>{go('send_excel',{code:openCycle.id});notify('Bot-এর Excel Telegram-এ পাঠানো হচ্ছে')}}><Send size={15}/>Excel → Telegram</button>
          {openCycle.s!=='ACTIVE'&&<button className="secondary" onClick={()=>setConfirm('reopen')}><RotateCcw size={15}/>Reopen</button>}
        </div>
        <div className="bk-month"><CalendarDays size={15}/><span>হিসাবের মাস</span><input type="month" value={month||openCycle.d.month} onChange={e=>setMonth(e.target.value)} aria-label="Payment month"/>{month&&month!==openCycle.d.month&&<button className="primary" onClick={()=>{go('set_month',{code:openCycle.id,month});setMonth('')}}>Save</button>}</div>
        {confirm==='reopen'&&<Confirm text={<>{openCycle.id} আবার Running হবে; এখনকার {active?.id} Completed হয়ে যাবে।</>} yes="Reopen" onYes={()=>{go('reopen_payment',{code:openCycle.id});setConfirm('')}} onNo={()=>setConfirm('')}/>}
      </section>
      <section className="panel xb-list"><TxTable rows={cycleTx} withCycle={false}/></section>
    </>}

    {tab==='receipts'&&<>
      <div className="bh-filters panel bk-filterbar"><div className="bh-search"><Search size={15}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Account, Transaction ID, তারিখ, amount বা BP-0001…" aria-label="Search receipts"/></div>
        <select value={range} onChange={e=>setRange(e.target.value)} aria-label="সময়"><option value="all">সব সময়</option><option value="today">আজ</option>{txMonths.map(m=><option key={m} value={m}>{monthLabel(m)}</option>)}</select>
        <button className="secondary" onClick={()=>downloadCsv('BURAQ-receipts',TX_HEAD,shownTx.map(txRow))}><Download size={15}/>CSV</button></div>
      <p className="bk-count">{num(shownTx.length)}টি receipt · {tk(shownTx.reduce((s,t)=>s+(t.a??0),0))}</p>
      <section className="panel xb-list"><TxTable rows={shownTx.slice(0,300)}/>{shownTx.length>300&&<p className="xb-none">প্রথম ৩০০টি দেখানো হচ্ছে — search দিয়ে ছোট করুন বা CSV নিন।</p>}</section>
    </>}

    {tab==='analytics'&&<>
      <Stats items={[['Receipts',num(an.n)],['মোট',tk(an.total)],['গড়',tk(an.avg)],['Payments',num(an.cycles)]]}/>
      <div className="xb-grid bk-grid2">
        <section className="panel xb-report"><h3 className="bk-h">Top receiver accounts</h3><ul>{an.top.map(r=><li key={r.key}><div><span className="mono">{r.key}</span><b>{tk(r.total)}</b></div><small className="bk-sub">{r.n}টি receipt</small><i style={{width:`${r.total/(an.top[0]?.total||1)*100}%`}}/></li>)}</ul></section>
        <section className="panel xb-report"><h3 className="bk-h">Bank summary</h3><ul>{an.banks.map(r=><li key={r.key}><div><span>{r.key}</span><b>{tk(r.total)}</b></div><small className="bk-sub">{r.n}টি receipt</small><i style={{width:`${r.total/(an.banks[0]?.total||1)*100}%`}}/></li>)}</ul>
          <h3 className="bk-h">মাস অনুযায়ী</h3><ul>{an.byMonth.map(r=><li key={r.key}><div><span>{monthLabel(r.key)}</span><b>{tk(r.total)}</b></div><i style={{width:`${r.total/Math.max(...an.byMonth.map(x=>x.total),1)*100}%`}}/></li>)}</ul></section>
      </div></>}

    {tab==='activity'&&<section className="panel xb-list">{!activity.length?<p className="xb-none">Activity log খালি।</p>:<table className="bh-table"><thead><tr><th>সময়</th><th>কাজ</th><th>বিস্তারিত</th></tr></thead><tbody>{activity.map(a=><tr key={a.id} className="static"><td className="t">{fmtDT(a.at)}</td><td className="title"><b>{a.t}</b></td><td className="type">{a.d.details}</td></tr>)}</tbody></table>}</section>}

    {tab==='tools'&&<>
      <div className="bk-tools">
        {[['doctor',Stethoscope,'System Doctor','Database, receipt file, backup আর OCR ঠিক আছে কিনা পরীক্ষা করে।'],['maintenance',Wrench,'Maintenance','পুরনো temp/export/backup পরিষ্কার আর database optimize করে।'],['backup',Archive,'Full backup','পুরো database আর receipt ছবির ZIP backup বানিয়ে Telegram-এ পাঠায়।'],['send_pdf',FileText,'সব payment-এর PDF','Bot-এর professional PDF report Telegram-এ পাঠায়।'],['resync',RefreshCw,'পুরো data আবার sync','Site-এ কিছু না মিললে bot সব data নতুন করে পাঠাবে।']].map(([a,Icon,t,d])=>{const I=Icon as typeof Wrench;return <button key={a as string} className="panel bk-tool" onClick={()=>{go(a as string);notify(`${t} bot-এ পাঠানো হয়েছে`)}}><I size={20}/><b>{t as string}</b><small>{d as string}</small></button>})}
      </div>
      {cmd.list.filter(c=>(c.action==='doctor'||c.action==='maintenance')&&c.status==='done').slice(0,1).map(c=><section key={c.id} className="panel bk-report"><div className="bk-sec-head"><h3>{LABELS[c.action]} · {fmtDT(c.doneAt??'')}</h3></div><pre>{c.result?.report}</pre></section>)}
    </>}

    <CommandLog list={cmd.list} labels={LABELS} describe={describe} cancel={cmd.cancel} lastSeen={botInfo?.lastSeenAt}/>
  </div>;
}
