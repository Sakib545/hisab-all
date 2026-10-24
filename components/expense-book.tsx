'use client';
import {useState,useMemo,useRef} from 'react';
import {Check,Trash2,Download,FileText,CircleAlert,Bot,PenLine,X} from 'lucide-react';
import {parseExpenses,parseAmountOnly,weekRange,monthRange,categoryTotals,EXPENSE_CATEGORIES} from '../lib/expense-parser';

type Entry={id:string;date:string;type:string;amount:number;category:string;party:string;account:string;reference:string;note:string};
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Dhaka'}).format(new Date());
const tk=(n:number)=>'৳'+(n/100).toLocaleString('en-BD',{maximumFractionDigits:2});
const BN_MONTHS=['জানুয়ারি','ফেব্রুয়ারি','মার্চ','এপ্রিল','মে','জুন','জুলাই','আগস্ট','সেপ্টেম্বর','অক্টোবর','নভেম্বর','ডিসেম্বর'];
const dm=(d:string)=>`${d.slice(8,10)}/${d.slice(5,7)}`;
type Period={key:string;label:string;from:string;to:string};

function periods(t:string):{quick:Period[];weeks:Period[];months:Period[]}{
  const w=(o:number):Period=>{const [a,b]=weekRange(o,t);return{key:`w${o}`,label:`${o===0?'চলতি সপ্তাহ':o===1?'গত সপ্তাহ':`${o} সপ্তাহ আগে`} (${dm(a)}–${dm(b)})`,from:a,to:b}};
  const m=(o:number):Period=>{const [a,b]=monthRange(o,t);const name=`${BN_MONTHS[Number(a.slice(5,7))-1]} ${a.slice(0,4)}`;return{key:`m${o}`,label:o===0?`চলতি মাস (${name})`:o===1?`গত মাস (${name})`:name,from:a,to:b}};
  return{quick:[{key:'today',label:'আজ',from:t,to:t},{...w(0),label:'এই সপ্তাহ'},{...m(0),label:'এই মাস'},{key:'all',label:'সব হিসাব',from:'0000',to:'9999'}],weeks:[...Array(8)].map((_,i)=>w(i)),months:[...Array(12)].map((_,i)=>m(i))};
}

function exportCsv(rows:Entry[],title:string){
  const esc=(s:string)=>`"${String(s).replace(/"/g,'""')}"`;
  const total=rows.reduce((a,r)=>a+r.amount,0);
  const lines=[['Date','Category','Amount','Source'].join(','),...rows.map(r=>[r.date,esc(r.category),(r.amount/100).toFixed(2),r.reference?.startsWith('tg:')?'Bot':'Web'].join(',')),'',['',esc('মোট'),(total/100).toFixed(2),''].join(',')];
  const blob=new Blob(['\uFEFF'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`business-expenses-${title.replace(/[^\w\u0980-\u09FF-]+/g,'-')}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);
}
function exportPdf(rows:Entry[],title:string){
  const totals=categoryTotals(rows);const total=rows.reduce((a,r)=>a+r.amount,0);
  const w=window.open('','_blank');if(!w)return;
  const e=(s:string)=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]!));
  w.document.write(`<!doctype html><html lang="bn"><meta charset="utf-8"><title>${e(title)}</title><style>body{font-family:"Noto Sans Bengali","Hind Siliguri",Inter,Arial,sans-serif;color:#1d2a24;margin:32px}h1{font-size:20px;margin:0}p{color:#6b756f;margin:4px 0 20px;font-size:12px}table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:22px}th{background:#24745b;color:#fff;text-align:left;padding:7px 9px}td{padding:6px 9px;border-bottom:1px solid #e3e8e5}td.r,th.r{text-align:right}tfoot td{font-weight:700;background:#eaf4ee}h2{font-size:14px;margin:0 0 8px}@media print{body{margin:12mm}}</style>
  <h1>ব্যবসার খরচ — ${e(title)}</h1><p>Nexa Hisab · ${rows.length}টি খরচ · তৈরি ${new Date().toLocaleString('en-GB',{timeZone:'Asia/Dhaka'})}</p>
  <h2>ক্যাটাগরি অনুযায়ী</h2><table><thead><tr><th>ক্যাটাগরি</th><th class="r">মোট</th></tr></thead><tbody>${totals.map(t=>`<tr><td>${e(t.category)}</td><td class="r">${tk(t.amount)}</td></tr>`).join('')}</tbody><tfoot><tr><td>সর্বমোট</td><td class="r">${tk(total)}</td></tr></tfoot></table>
  <h2>বিস্তারিত</h2><table><thead><tr><th>তারিখ</th><th>ক্যাটাগরি</th><th class="r">পরিমাণ</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.date.split('-').reverse().join('/')}</td><td>${e(r.category)}</td><td class="r">${tk(r.amount)}</td></tr>`).join('')}</tbody><tfoot><tr><td></td><td>মোট</td><td class="r">${tk(total)}</td></tr></tfoot></table>
  <script>onload=()=>setTimeout(()=>print(),300)<\/script></html>`);
  w.document.close();
}

export default function ExpenseBook({rows,reload,notify}:{rows:Entry[];reload:()=>Promise<void>|void;notify:(s:string)=>void}){
  const t=today();const P=useMemo(()=>periods(t),[t]);
  const [text,setText]=useState(''),[date,setDate]=useState(t),[pending,setPending]=useState<number|null>(null),[custom,setCustom]=useState(''),[saving,setSaving]=useState(false),[err,setErr]=useState(''),
    [period,setPeriod]=useState<Period>(P.quick[2]),[confirm,setConfirm]=useState(''),[exp,setExp]=useState(false),[expPeriod,setExpPeriod]=useState('m0');
  const input=useRef<HTMLTextAreaElement>(null);
  const expenses=useMemo(()=>rows.filter(r=>r.type==='expense').sort((a,b)=>b.date.localeCompare(a.date)),[rows]);
  const inPeriod=(p:Period)=>expenses.filter(r=>r.date>=p.from&&r.date<=p.to);
  const shown=inPeriod(period);
  const totals=categoryTotals(shown);const grand=shown.reduce((a,r)=>a+r.amount,0);const max=Math.max(1,...totals.map(x=>x.amount));
  const recentCustom=[...new Set(expenses.map(r=>r.category).filter(c=>!EXPENSE_CATEGORIES.includes(c)))].slice(0,6);
  const parsed=parseExpenses(text);const amountOnly=parsed.length?null:parseAmountOnly(text);

  async function save(list:{amount:number;category:string}[]){
    setSaving(true);setErr('');let done=0;
    try{for(const x of list){const r=await fetch('/api/entries',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'expense',amount:Math.round(x.amount*100),date,category:x.category,account:'Cash',party:'',note:'খরচের খাতা'})});const d=await r.json() as {error?:string};if(!r.ok)throw Error(d.error||'Save হয়নি');done++}
      await reload();setText('');setPending(null);setCustom('');notify(list.length>1?`✅ ${list.length}টি খরচ সেভ হয়েছে · মোট ${tk(list.reduce((a,x)=>a+x.amount*100,0))}`:`✅ খরচ সেভ হয়েছে · ${list[0].category} · ${tk(list[0].amount*100)}`);input.current?.focus();
    }catch(e){setErr(`${done?`${done}টি সেভ হয়েছে, বাকিগুলো হয়নি: `:''}${String(e).replace(/^Error: /,'')}`);if(done)reload()}finally{setSaving(false)}
  }
  function submit(){if(parsed.length)save(parsed);else if(amountOnly){setPending(amountOnly);}else if(text.trim())setErr('বুঝতে পারিনি। এভাবে লিখুন: 500 খাবার — অথবা একসাথে: 500 খরচ 300 খাবার');}
  async function remove(r:Entry){const res=await fetch(`/api/entries?id=${r.id}`,{method:'DELETE'});if(res.ok){setConfirm('');await reload();notify(`🗑️ Delete হয়েছে · ${r.category} · ${tk(r.amount)}`)}else notify('Delete করা যায়নি।')}
  const exportRows=()=>{const p=[...P.quick,...P.weeks,...P.months].find(x=>x.key===expPeriod)!;return{p,rows:[...inPeriod(p)].sort((a,b)=>a.date.localeCompare(b.date))}};

  return <div className="bh xb">
    <div className="title-row"><div><h1>খরচের খাতা</h1><p className="subtitle">Telegram bot-এর মতোই লিখুন — <b>500 খাবার</b> বা একসাথে <b>500 খরচ 300 নাস্তা</b>।</p></div>
      <div className="bh-head-actions"><button className="secondary" onClick={()=>setExp(!exp)} aria-expanded={exp}><Download size={16}/>Export PDF / Excel</button></div></div>

    {exp&&<section className="panel xb-export"><label className="bh-field">কোন সময়ের হিসাব<select value={expPeriod} onChange={e=>setExpPeriod(e.target.value)}>
      <optgroup label="Monthly">{P.months.map(p=><option key={p.key} value={p.key}>{p.label}</option>)}</optgroup>
      <optgroup label="Weekly">{P.weeks.map(p=><option key={p.key} value={p.key}>{p.label}</option>)}</optgroup>
      <option value="today">আজ</option><option value="all">সব হিসাব</option></select></label>
      <div className="xb-export-actions"><span>{exportRows().rows.length}টি খরচ · {tk(exportRows().rows.reduce((a,r)=>a+r.amount,0))}</span>
        <button className="secondary" disabled={!exportRows().rows.length} onClick={()=>{const {p,rows}=exportRows();exportPdf(rows,p.label)}}><FileText size={15}/>PDF</button>
        <button className="primary" disabled={!exportRows().rows.length} onClick={()=>{const {p,rows}=exportRows();exportCsv(rows,p.label)}}><Download size={15}/>Excel (CSV)</button>
        <button className="bh-icon" onClick={()=>setExp(false)} aria-label="Close export"><X size={15}/></button></div></section>}

    <section className="panel xb-entry">
      <div className="xb-entry-row">
        <textarea ref={input} rows={1} value={text} onChange={e=>{setText(e.target.value);setErr('');setPending(null)}} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submit()}}} placeholder="500 খাবার 300 নাস্তা" aria-label="খরচ লিখুন" autoFocus/>
        <input type="date" value={date} max={t} onChange={e=>setDate(e.target.value)} aria-label="তারিখ"/>
        <button className="primary" disabled={saving||(!parsed.length&&!amountOnly)} onClick={submit}>{saving?'Saving…':parsed.length>1?`Save ${parsed.length}টি খরচ`:'Save'}</button>
      </div>
      {parsed.length>0&&<div className="xb-preview" aria-live="polite">{parsed.map((p,i)=><span key={i} className={EXPENSE_CATEGORIES.includes(p.category)?'':'new'}><Check size={13}/>{tk(p.amount*100)} · {p.category}{!EXPENSE_CATEGORIES.includes(p.category)&&<em>নতুন ক্যাটাগরি</em>}</span>)}{parsed.length>1&&<b>মোট {tk(parsed.reduce((a,p)=>a+p.amount*100,0))}</b>}</div>}
      {pending!==null&&<div className="xb-pick"><p>💰 {tk(pending*100)} — এটা কিসের টাকা?</p><div>{[...EXPENSE_CATEGORIES,...recentCustom].map(c=><button key={c} disabled={saving} onClick={()=>save([{amount:pending,category:c}])}>{c}</button>)}</div>
        <div className="xb-custom"><input value={custom} onChange={e=>setCustom(e.target.value)} placeholder="অন্য কিছু লিখুন…" maxLength={80} onKeyDown={e=>{if(e.key==='Enter'&&custom.trim())save([{amount:pending,category:custom.trim()}])}}/><button className="secondary" disabled={!custom.trim()||saving} onClick={()=>save([{amount:pending,category:custom.trim()}])}>Save</button><button className="bh-icon" onClick={()=>setPending(null)} aria-label="Cancel">❌</button></div></div>}
      {err&&<p className="bh-error" role="alert"><CircleAlert size={15}/>{err}</p>}
    </section>

    <div className="xb-periods" role="tablist">{P.quick.map(p=><button key={p.key} role="tab" aria-selected={period.key===p.key} className={period.key===p.key?'on':''} onClick={()=>setPeriod(p)}>{p.label}</button>)}
      <select value={P.months.some(m=>m.key===period.key)&&period.key!=='m0'?period.key:''} onChange={e=>{const m=P.months.find(x=>x.key===e.target.value);if(m)setPeriod(m)}} aria-label="অন্য মাস"><option value="">অন্য মাস…</option>{P.months.slice(1).map(m=><option key={m.key} value={m.key}>{m.label}</option>)}</select></div>

    <div className="xb-grid">
      <section className="panel xb-report" aria-label="ক্যাটাগরি অনুযায়ী মোট">
        <div className="xb-total"><span>{period.key==='all'?'সব হিসাব':period.label}</span><b>{tk(grand)}</b><small>{shown.length}টি খরচ</small></div>
        {!totals.length?<p className="xb-none">এই সময়ে কোনো খরচ পাওয়া যায়নি।</p>:<ul>{totals.map(x=><li key={x.category}><div><span>{x.category}{x.custom&&<em>custom</em>}</span><b>{tk(x.amount)}</b></div><i style={{width:`${x.amount/max*100}%`}}/></li>)}</ul>}
      </section>
      <section className="panel xb-list" aria-label="খরচের তালিকা">
        {!shown.length?<p className="xb-none">খরচ লিখলে এখানে দেখাবে। Telegram bot connect থাকলে bot-এর খরচও আসবে।</p>:
        <table className="bh-table"><thead><tr><th>তারিখ</th><th>ক্যাটাগরি</th><th>কোথা থেকে</th><th className="r">পরিমাণ</th><th aria-label="Actions"/></tr></thead><tbody>
          {shown.map(r=>{const fromBot=r.reference?.startsWith('tg:');return <tr key={r.id} className="static">
            <td className="t">{r.date.split('-').reverse().join('/')}</td>
            <td className="title"><b>{r.category}</b>{r.party&&r.party!==r.category&&<small>{r.party}</small>}</td>
            <td>{fromBot?<span className="xb-src bot"><Bot size={12}/>{r.reference.split(':')[1]}</span>:<span className="xb-src"><PenLine size={12}/>Web</span>}</td>
            <td className="r amt">{tk(r.amount)}</td>
            <td className="xb-act">{confirm===r.id?<span className="xb-confirm">{fromBot&&<small>Bot-এর Sheet থেকেও মুছুন, নইলে পরের sync-এ ফিরে আসবে।</small>}<button className="danger solid" onClick={()=>remove(r)}>Delete</button><button className="secondary" onClick={()=>setConfirm('')}>না</button></span>:<button className="bh-gear static" onClick={()=>setConfirm(r.id)} aria-label={`Delete ${r.category}`}><Trash2 size={15}/></button>}</td>
          </tr>})}
        </tbody></table>}
      </section>
    </div>
  </div>;
}
