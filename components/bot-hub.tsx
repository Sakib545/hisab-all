'use client';
import {useState,useEffect,useRef,useCallback} from 'react';
import {Bot,Plus,Upload,Search,X,Copy,Check,RefreshCw,KeyRound,Trash2,Settings2,Radio,FileUp,ArrowLeft,CircleAlert,BookOpen} from 'lucide-react';
import {parseCsv,guessMapping,type ColumnMap} from '../lib/bot-sync';

type Stats={records:number;amount:number;ledger:number;ledgerAmount:number;week:number;latest:string|null};
type BotRow={id:string;name:string;label:string;kind:string;tokenHint:string|null;createdAt:string;lastSeenAt:string|null;lastError:string|null;stats:Stats};
type Rec={id:string;bot:string;externalId:string;kind:string;title:string;amount:number|null;status:string;data:string;occurredAt:string;receivedAt:string;entryId:string|null};
type Daily={bot:string;day:string;n:number};

const KINDS:Record<string,{label:string;hint:string}>={
  finance:{label:'Payments & money',hint:'Receipts, bank payments, income, expenses. Amounts can go straight into your ledger.'},
  orders:{label:'Orders & customers',hint:'Order bots, Messenger/Page bots, delivery updates.'},
  general:{label:'Anything else',hint:'Activity logs, users, cleanup results — any data your bot produces.'},
};
const money=(n:number)=>'৳ '+(n/100).toLocaleString('en-BD',{maximumFractionDigits:2});
const fmtTime=(iso:string)=>new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Dhaka',day:'numeric',month:'short',hour:'numeric',minute:'2-digit'}).format(new Date(iso));
function ago(iso:string|null){if(!iso)return '';const s=(Date.now()-Date.parse(iso))/1000;if(s<60)return 'just now';if(s<3600)return `${Math.floor(s/60)} min ago`;if(s<86400)return `${Math.floor(s/3600)} h ago`;return `${Math.floor(s/86400)} d ago`}
function health(b:BotRow):{key:'live'|'today'|'quiet'|'new';label:string}{
  if(!b.lastSeenAt)return{key:'new',label:'Waiting for first data'};
  const s=(Date.now()-Date.parse(b.lastSeenAt))/1000;
  return s<900?{key:'live',label:'Live'}:s<86400?{key:'today',label:`Active ${ago(b.lastSeenAt)}`}:{key:'quiet',label:`Quiet · last ${ago(b.lastSeenAt)}`};
}
const initials=(s:string)=>s.split(/[\s_-]+/).map(w=>w[0]).join('').slice(0,2).toUpperCase()||'B';
async function api<T>(url:string,init?:RequestInit):Promise<T>{const r=await fetch(url,init?{...init,headers:{'Content-Type':'application/json'}}:undefined);const d=await r.json() as T&{error?:string};if(!r.ok)throw Error(d.error||'Request failed');return d}

function CopyBox({text,label,multiline}:{text:string;label:string;multiline?:boolean}){
  const [done,setDone]=useState(false);
  return <div className={'bh-copy'+(multiline?' multi':'')}><pre aria-label={label}>{text}</pre><button type="button" onClick={async()=>{await navigator.clipboard.writeText(text);setDone(true);setTimeout(()=>setDone(false),1600)}} aria-label={`Copy ${label}`}>{done?<Check size={15}/>:<Copy size={15}/>}{done?'Copied':'Copy'}</button></div>;
}

function Spark({bot,daily}:{bot:string;daily:Daily[]}){
  const days=[...Array(14)].map((_,i)=>new Date(Date.now()-(13-i)*864e5).toISOString().slice(0,10));
  const vals=days.map(d=>daily.find(x=>x.bot===bot&&x.day===d)?.n??0);const max=Math.max(1,...vals);
  return <div className="bh-spark" aria-label={`${vals.reduce((a,b)=>a+b,0)} records in the last 14 days`}>{vals.map((v,i)=><i key={i} style={{height:`${v?Math.max(14,v/max*100):6}%`}} className={v?'on':''} title={`${days[i]}: ${v}`}/>)}</div>;
}

function SetupSnippets({token,origin,name,kind}:{token:string;origin:string;name:string;kind:string}){
  const [tab,setTab]=useState<'python'|'curl'>('python');
  const env=`NEXA_URL=${origin}\nNEXA_TOKEN=${token||'nxh_…your token…'}`;
  const py=kind==='finance'
    ?`from nexa_sync import NexaSync\nnexa = NexaSync()   # reads NEXA_URL + NEXA_TOKEN\n\n# after your bot saves a payment:\nnexa.record(\n    id=receipt_id,            # your bot's own unique id\n    title="Pubali → Rahim",\n    amount=1250.50,           # taka\n    ledger="expense",         # also adds it to the ledger\n    account="Pubali",\n    data={"trx": trx_id},\n)`
    :`from nexa_sync import NexaSync\nnexa = NexaSync()   # reads NEXA_URL + NEXA_TOKEN\n\n# anywhere in your bot:\nnexa.record(\n    id=f"user-{user.id}-{event_id}",\n    title="Left 34 channels",\n    kind="cleanup",\n    data={"user": user.id, "left": 34},\n)`;
  const curl=`curl -X POST ${origin}/api/bot/ingest \\\n  -H "Authorization: Bearer ${token||'$NEXA_TOKEN'}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"records":[{"id":"r-1","title":"Test from ${name}","amount":100}]}'`;
  return <div className="bh-snippets">
    <div className="bh-step-label"><b>1</b>Add these two lines to your bot's environment (.env, Railway or Render variables)</div>
    <CopyBox text={env} label="environment variables" multiline/>
    <div className="bh-step-label"><b>2</b>Send data from your bot</div>
    <div className="bh-seg" role="tablist">{(['python','curl'] as const).map(t=><button key={t} role="tab" aria-selected={tab===t} className={tab===t?'on':''} onClick={()=>setTab(t)}>{t==='python'?'Python bot':'Any language (HTTP)'}</button>)}</div>
    {tab==='python'?<><p className="bh-note">Copy <code>integrations/telegram/nexa_sync.py</code> into your bot folder. No extra packages needed. If this app is offline, records wait in a local queue and are sent later.</p><CopyBox text={py} label="Python code" multiline/></>:<CopyBox text={curl} label="curl command" multiline/>}
  </div>;
}

function ConnectWizard({onClose,onDone,origin}:{onClose:()=>void;onDone:()=>void;origin:string}){
  const [step,setStep]=useState(1),[label,setLabel]=useState(''),[kind,setKind]=useState('finance'),[err,setErr]=useState(''),[busy,setBusy]=useState(false),[created,setCreated]=useState<{name:string;token:string}|null>(null),[seen,setSeen]=useState<BotRow|null>(null);
  async function create(){setBusy(true);setErr('');try{const d=await api<{name:string;token:string}>('/api/bots',{method:'POST',body:JSON.stringify({label,kind})});setCreated(d);setStep(2);onDone()}catch(e){setErr(String(e).replace(/^Error: /,''))}finally{setBusy(false)}}
  useEffect(()=>{if(step!==3||!created)return;const t=setInterval(async()=>{try{const d=await api<{bots:BotRow[]}>('/api/bots');const b=d.bots.find(x=>x.name===created.name);if(b?.lastSeenAt){setSeen(b);onDone();clearInterval(t)}}catch{}},3000);return()=>clearInterval(t)},[step,created,onDone]);
  return <div className="bh-wizard">
    <ol className="bh-progress" aria-label="Connection steps">{['Name your bot','Copy the setup','Check connection'].map((s,i)=><li key={s} className={step>i+1?'done':step===i+1?'now':''}><span>{step>i+1?<Check size={12}/>:i+1}</span>{s}</li>)}</ol>
    {step===1&&<div className="bh-pane">
      <label className="bh-field">Bot name<input autoFocus value={label} onChange={e=>setLabel(e.target.value)} placeholder="e.g. BankTracker, Buraq Oil orders" maxLength={60} onKeyDown={e=>{if(e.key==='Enter'&&label.trim())create()}}/></label>
      <fieldset className="bh-kinds"><legend>What does this bot send?</legend>{Object.entries(KINDS).map(([k,v])=><label key={k} className={kind===k?'on':''}><input type="radio" name="kind" value={k} checked={kind===k} onChange={()=>setKind(k)}/><b>{v.label}</b><small>{v.hint}</small></label>)}</fieldset>
      {err&&<p className="bh-error" role="alert"><CircleAlert size={15}/>{err}</p>}
      <div className="bh-actions"><button className="secondary" onClick={onClose}>Cancel</button><button className="primary" disabled={!label.trim()||busy} onClick={create}>{busy?'Creating…':'Create bot key'}</button></div>
    </div>}
    {step===2&&created&&<div className="bh-pane">
      <div className="bh-keynote"><KeyRound size={17}/><div><b>This key is shown only once.</b> Copy it now. If you lose it, make a new one from the bot's settings.</div></div>
      <SetupSnippets token={created.token} origin={origin} name={created.name} kind={kind}/>
      <div className="bh-actions"><button className="secondary" onClick={onClose}>Finish later</button><button className="primary" onClick={()=>setStep(3)}>I've added it — check connection</button></div>
    </div>}
    {step===3&&<div className="bh-pane bh-listen">
      {seen?<><div className="bh-ok"><Check size={26}/></div><h3>{seen.label} is connected</h3><p>{seen.stats.records?`${seen.stats.records} record${seen.stats.records>1?'s':''} received.`:'Connection test received.'} New data will appear in the activity list as it arrives.</p><div className="bh-actions center"><button className="primary" onClick={onClose}>Done</button></div></>
      :<><div className="bh-radar"><Radio size={26}/></div><h3>Waiting for your bot…</h3><p>Restart your bot after adding the variables, then send one record (or run <code>python nexa_sync.py test</code>). This page checks every few seconds.</p><div className="bh-actions center"><button className="secondary" onClick={()=>setStep(2)}><ArrowLeft size={15}/>Back to setup</button><button className="secondary" onClick={onClose}>Close</button></div></>}
    </div>}
  </div>;
}

function ImportPanel({bots,initial,onClose,onDone}:{bots:BotRow[];initial:string;onClose:()=>void;onDone:(msg:string)=>void}){
  const [bot,setBot]=useState(initial||bots[0]?.name||''),[rows,setRows]=useState<string[][]>([]),[file,setFile]=useState(''),[map,setMap]=useState<ColumnMap>({id:'',at:'',amount:'',title:'',status:''}),[ledger,setLedger]=useState(''),[account,setAccount]=useState(''),[err,setErr]=useState(''),[progress,setProgress]=useState<{done:number;total:number;created:number;dup:number;failed:number}|null>(null);
  const headers=rows[0]??[],body=rows.slice(1);
  async function read(f:File){setErr('');setFile(f.name);const text=await f.text();try{
    let r:string[][];
    if(/\.json$/i.test(f.name)){const j=JSON.parse(text);const arr:Record<string,unknown>[]=Array.isArray(j)?j:(j.records??j.data??[]);if(!arr.length)throw Error('JSON-এ কোনো row পাওয়া যায়নি।');const keys=[...new Set(arr.flatMap(o=>Object.keys(o)))];r=[keys,...arr.map(o=>keys.map(k=>o[k]==null?'':typeof o[k]==='object'?JSON.stringify(o[k]):String(o[k])))];}
    else r=parseCsv(text);
    if(r.length<2)throw Error('File-এ header ছাড়া কোনো row নেই।');setRows(r);setMap(guessMapping(r[0]));
  }catch(e){setRows([]);setErr(String(e).replace(/^Error: /,'').replace(/^SyntaxError: /,'JSON ঠিক নেই: '))}}
  const col=(k:keyof ColumnMap,row:string[])=>map[k]?row[headers.indexOf(map[k])]??'':'';
  function toRecords(){return body.map((row,i)=>{const data:Record<string,string>={};headers.forEach((h,j)=>{if(row[j]!==undefined&&row[j]!=='')data[h]=row[j]});const amt=col('amount',row);
    return {id:col('id',row)||`import-${file}-${i+1}`,title:col('title',row)||undefined,at:col('at',row)||undefined,amount:amt||undefined,status:col('status',row)||undefined,kind:'import',data,ledger:ledger&&amt?{type:ledger,account:account||undefined,party:col('title',row)||undefined}:undefined}})}
  async function run(){const recs=toRecords();const p={done:0,total:recs.length,created:0,dup:0,failed:0};setProgress({...p});setErr('');
    try{for(let i=0;i<recs.length;i+=100){const d=await api<{created:number;duplicate:number;failed:number;results:{status:string;error?:string}[]}>('/api/bots/records',{method:'POST',body:JSON.stringify({bot,records:recs.slice(i,i+100)})});p.done+=Math.min(100,recs.length-i);p.created+=d.created;p.dup+=d.duplicate;p.failed+=d.failed;setProgress({...p});if(d.failed&&!err){const f=d.results.find(r=>r.status==='error');if(f)setErr(`কিছু row বাদ গেছে: ${f.error}`)}}
      onDone(`Imported ${p.created} · skipped ${p.dup} duplicate${p.failed?` · ${p.failed} rejected`:''}`)}catch(e){setErr(String(e).replace(/^Error: /,''))}}
  if(!bots.length)return <div className="bh-pane"><p>Import করার আগে একটা bot যোগ করুন — data কোন bot-এর সেটা জানতে হবে।</p><div className="bh-actions"><button className="secondary" onClick={onClose}>Close</button></div></div>;
  return <div className="bh-pane">
    <label className="bh-field">Import into<select value={bot} onChange={e=>setBot(e.target.value)}>{bots.map(b=><option key={b.name} value={b.name}>{b.label}</option>)}</select></label>
    <label className="bh-drop" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const f=e.dataTransfer.files[0];if(f)read(f)}}>
      <FileUp size={24}/><b>{file||'Drop a CSV or JSON file, or click to choose'}</b><small>{file?`${body.length} rows found`:'Export from your bot (Excel → Save as CSV) or the bot’s database. Same rows imported twice are skipped.'}</small>
      <input type="file" accept=".csv,.json,text/csv,application/json" onChange={e=>{const f=e.target.files?.[0];if(f)read(f)}}/>
    </label>
    {headers.length>0&&<>
      <div className="bh-map">{(['id','at','amount','title','status'] as (keyof ColumnMap)[]).map(k=><label key={k} className="bh-field">{({id:'Unique ID',at:'Date / time',amount:'Amount (৳)',title:'Title / name',status:'Status'})[k]}<select value={map[k]} onChange={e=>setMap({...map,[k]:e.target.value})}><option value="">— none —</option>{headers.map(h=><option key={h} value={h}>{h}</option>)}</select></label>)}</div>
      {!map.id&&<p className="bh-hint">Unique ID column না দিলে file-এর নাম আর row নম্বর দিয়ে ID বানানো হবে। একই file আবার import করলে skip হবে, কিন্তু নাম বা row-এর ক্রম বদলালে duplicate হতে পারে।</p>}
      <div className="bh-map two"><label className="bh-field">Add amounts to ledger<select value={ledger} onChange={e=>setLedger(e.target.value)} disabled={!map.amount}><option value="">No, keep in bot data only</option><option value="expense">Yes, as expenses</option><option value="income">Yes, as income</option></select></label>{ledger&&<label className="bh-field">Account<input value={account} onChange={e=>setAccount(e.target.value)} placeholder="e.g. Pubali, bKash"/></label>}</div>
      <div className="bh-preview" role="region" aria-label="Preview"><table><thead><tr><th>ID</th><th>Date</th><th>Title</th><th className="r">Amount</th></tr></thead><tbody>{body.slice(0,5).map((r,i)=><tr key={i}><td>{col('id',r)||<em>auto</em>}</td><td>{col('at',r)||<em>now</em>}</td><td>{col('title',r)||'—'}</td><td className="r">{col('amount',r)||'—'}</td></tr>)}</tbody></table>{body.length>5&&<small>…and {body.length-5} more rows</small>}</div>
    </>}
    {progress&&<div className="bh-bar" role="progressbar" aria-valuenow={progress.done} aria-valuemax={progress.total}><i style={{width:`${progress.done/progress.total*100}%`}}/><span>{progress.done}/{progress.total} · {progress.created} new · {progress.dup} skipped{progress.failed?` · ${progress.failed} rejected`:''}</span></div>}
    {err&&<p className="bh-error" role="alert"><CircleAlert size={15}/>{err}</p>}
    <div className="bh-actions"><button className="secondary" onClick={onClose}>{progress?.done===progress?.total&&progress?'Close':'Cancel'}</button><button className="primary" disabled={!body.length||!bot||(!!progress&&progress.done<progress.total)} onClick={run}><Upload size={15}/>Import {body.length||''} rows</button></div>
  </div>;
}

function BotSettings({b,origin,onClose,onChanged,notify}:{b:BotRow;origin:string;onClose:()=>void;onChanged:()=>void;notify:(s:string)=>void}){
  const [label,setLabel]=useState(b.label),[kind,setKind]=useState(b.kind),[token,setToken]=useState(''),[confirm,setConfirm]=useState(false),[purge,setPurge]=useState(false),[err,setErr]=useState('');
  const act=async(f:()=>Promise<void>)=>{setErr('');try{await f()}catch(e){setErr(String(e).replace(/^Error: /,''))}};
  return <div className="bh-pane">
    <div className="bh-map two"><label className="bh-field">Name<input value={label} onChange={e=>setLabel(e.target.value)} maxLength={60}/></label><label className="bh-field">Type<select value={kind} onChange={e=>setKind(e.target.value)}>{Object.entries(KINDS).map(([k,v])=><option key={k} value={k}>{v.label}</option>)}</select></label></div>
    <div className="bh-actions left"><button className="secondary" disabled={label===b.label&&kind===b.kind} onClick={()=>act(async()=>{await api('/api/bots',{method:'POST',body:JSON.stringify({id:b.id,action:'rename',label,kind})});onChanged();notify('Bot saved')})}>Save changes</button></div>
    <h4>Bot key</h4>
    {token?<><div className="bh-keynote"><KeyRound size={17}/><div><b>New key — shown only once.</b> The old key stopped working. Update <code>NEXA_TOKEN</code> in your bot and restart it.</div></div><SetupSnippets token={token} origin={origin} name={b.name} kind={b.kind}/></>
    :<><p className="bh-note">{b.tokenHint?<>Current key ends in <code>…{b.tokenHint}</code>.</>:'This bot uses the shared BOT_SYNC_TOKEN.'} Make a new key if the old one leaked or got lost.</p><div className="bh-actions left"><button className="secondary" onClick={()=>act(async()=>{const d=await api<{token:string}>('/api/bots',{method:'POST',body:JSON.stringify({id:b.id,action:'rotate'})});setToken(d.token);onChanged()})}><RefreshCw size={15}/>Make new key</button></div></>}
    <h4>Remove bot</h4>
    {!confirm?<div className="bh-actions left"><button className="danger" onClick={()=>setConfirm(true)}><Trash2 size={15}/>Remove {b.label}</button></div>
    :<div className="bh-confirm"><p>The bot's key stops working immediately.</p><label><input type="checkbox" checked={purge} onChange={e=>setPurge(e.target.checked)}/> Also delete its {b.stats.records} records here (ledger transactions stay)</label><div className="bh-actions left"><button className="secondary" onClick={()=>setConfirm(false)}>Keep bot</button><button className="danger solid" onClick={()=>act(async()=>{await api(`/api/bots?id=${b.id}${purge?'&purge=1':''}`,{method:'DELETE'});onChanged();onClose();notify(`${b.label} removed`)})}>Remove bot</button></div></div>}
    {err&&<p className="bh-error" role="alert"><CircleAlert size={15}/>{err}</p>}
  </div>;
}

function RecordDrawer({r,bot,onClose,onDeleted}:{r:Rec;bot?:BotRow;onClose:()=>void;onDeleted:()=>void}){
  let data:Record<string,unknown>={};try{data=JSON.parse(r.data)}catch{}
  const [confirm,setConfirm]=useState(false);
  return <div className="bh-detail">
    <dl>
      <div><dt>Bot</dt><dd>{bot?.label??r.bot}</dd></div>
      <div><dt>Happened</dt><dd>{fmtTime(r.occurredAt)}</dd></div>
      <div><dt>Received</dt><dd>{fmtTime(r.receivedAt)}</dd></div>
      <div><dt>Type</dt><dd>{r.kind}{r.status&&` · ${r.status}`}</dd></div>
      {r.amount!==null&&<div><dt>Amount</dt><dd>{money(r.amount)}</dd></div>}
      <div><dt>Ledger</dt><dd>{r.entryId?<span className="bh-in-ledger"><Check size={13}/>In Transactions</span>:'Not in ledger'}</dd></div>
      <div><dt>Bot ID</dt><dd><code>{r.externalId}</code></dd></div>
    </dl>
    {Object.keys(data).length>0&&<><h4>Data from the bot</h4><dl className="bh-data">{Object.entries(data).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{typeof v==='object'?<code>{JSON.stringify(v)}</code>:String(v)}</dd></div>)}</dl></>}
    <div className="bh-actions left">{!confirm?<button className="danger" onClick={()=>setConfirm(true)}><Trash2 size={15}/>Delete record</button>:<><button className="secondary" onClick={()=>setConfirm(false)}>Keep</button><button className="danger solid" onClick={async()=>{await api(`/api/bots/records?id=${r.id}`,{method:'DELETE'});onDeleted();onClose()}}>Delete{r.entryId?' (ledger entry stays)':''}</button></>}</div>
  </div>;
}

function Modal({title,onClose,wide,children}:{title:string;onClose:()=>void;wide?:boolean;children:React.ReactNode}){
  useEffect(()=>{const k=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};addEventListener('keydown',k);return()=>removeEventListener('keydown',k)},[onClose]);
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><div className={'modal bh-modal'+(wide?' wide':'')} role="dialog" aria-modal="true" aria-label={title}><div className="bh-modal-head"><h2>{title}</h2><button onClick={onClose} aria-label="Close"><X size={19}/></button></div>{children}</div></div>;
}

export default function BotHub({notify,onLedgerChange}:{notify:(s:string)=>void;onLedgerChange:()=>void}){
  const [bots,setBots]=useState<BotRow[]>([]),[daily,setDaily]=useState<Daily[]>([]),[recs,setRecs]=useState<Rec[]>([]),[kinds,setKinds]=useState<{kind:string;n:number}[]>([]),[more,setMore]=useState(false),[loading,setLoading]=useState(true),[err,setErr]=useState(''),
    [sel,setSel]=useState(''),[kind,setKind]=useState(''),[q,setQ]=useState(''),[modal,setModal]=useState<null|{t:'connect'}|{t:'import'}|{t:'settings';b:BotRow}|{t:'record';r:Rec}>(null),[origin,setOrigin]=useState('');
  const qRef=useRef(q);qRef.current=q;
  useEffect(()=>setOrigin(location.origin),[]);
  const loadBots=useCallback(async()=>{try{const d=await api<{bots:BotRow[];daily:Daily[]}>('/api/bots');setBots(d.bots);setDaily(d.daily);setErr('')}catch(e){setErr(String(e).replace(/^Error: /,''))}},[]);
  const loadRecs=useCallback(async(append=false,before='')=>{const p=new URLSearchParams({limit:'50'});if(sel)p.set('bot',sel);if(kind)p.set('kind',kind);if(qRef.current.trim())p.set('q',qRef.current.trim());if(before)p.set('before',before);
    try{const d=await api<{records:Rec[];more:boolean;kinds:{kind:string;n:number}[]}>('/api/bots/records?'+p);setRecs(x=>append?[...x,...d.records]:d.records);setMore(d.more);setKinds(d.kinds)}catch(e){setErr(String(e).replace(/^Error: /,''))}finally{setLoading(false)}},[sel,kind]);
  const refresh=useCallback(()=>{loadBots();loadRecs()},[loadBots,loadRecs]);
  useEffect(()=>{loadBots()},[loadBots]);
  useEffect(()=>{loadRecs()},[loadRecs]);
  useEffect(()=>{const t=setTimeout(()=>loadRecs(),300);return()=>clearTimeout(t)},[q]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{const t=setInterval(()=>{if(document.visibilityState==='visible'&&!modal)refresh()},30000);return()=>clearInterval(t)},[refresh,modal]);

  const byName=Object.fromEntries(bots.map(b=>[b.name,b]));
  const live=bots.filter(b=>health(b).key==='live').length;
  const week=bots.reduce((a,b)=>a+(b.stats.week||0),0);
  const synced=bots.reduce((a,b)=>a+(b.stats.records||0),0);
  const lastSeen=bots.map(b=>b.lastSeenAt).filter(Boolean).sort().pop()??null;
  const close=()=>setModal(null);

  return <div className="bh">
    <div className="title-row"><div><h1>Telegram bots</h1><p className="subtitle">আপনার সব bot-এর data এক জায়গায় — live sync বা file import।</p></div>
      <div className="bh-head-actions"><button className="secondary" onClick={()=>setModal({t:'import'})}><Upload size={16}/>Import data</button><button className="primary" onClick={()=>setModal({t:'connect'})}><Plus size={17}/>Connect a bot</button></div></div>

    {err&&<p className="bh-error banner" role="alert"><CircleAlert size={16}/>{err}</p>}

    {!loading&&!bots.length&&!err?<section className="bh-empty">
      <div className="bh-empty-art" aria-hidden><Bot size={34}/></div>
      <div><h2>Connect your first bot</h2><p>Give it a name, paste two lines into its settings, and its data starts showing up here. Payments can go straight into your ledger, and nothing is saved twice.</p>
      <div className="bh-actions left"><button className="primary" onClick={()=>setModal({t:'connect'})}><Plus size={17}/>Connect a bot</button><a className="secondary" href="#bh-help"><BookOpen size={15}/>How it works</a></div></div>
    </section>:<>
    <section className="bh-summary" aria-label="Summary">
      <div><span>Bots</span><b>{bots.length}</b><small>{live?`${live} live now`:'none live right now'}</small></div>
      <div><span>Records, last 7 days</span><b>{week.toLocaleString('en-BD')}</b><small>{synced.toLocaleString('en-BD')} stored in total</small></div>
      <div><span>Sent to ledger</span><b>{money(bots.reduce((a,b)=>a+(b.stats.ledgerAmount||0),0))}</b><small>{bots.reduce((a,b)=>a+(b.stats.ledger||0),0)} transactions from bots</small></div>
      <div><span>Last activity</span><b>{lastSeen?ago(lastSeen):'—'}</b><small>{lastSeen?fmtTime(lastSeen):'no data yet'}</small></div>
    </section>

    <div className="bh-grid">
      <aside className="bh-roster" aria-label="Bots">
        <button className={'bh-all'+(sel===''?' on':'')} onClick={()=>setSel('')}>All bots<span>{synced}</span></button>
        {bots.map(b=>{const h=health(b);return <div key={b.id} className={'bh-bot k-'+b.kind+(sel===b.name?' on':'')}>
          <button className="bh-bot-main" onClick={()=>setSel(sel===b.name?'':b.name)} aria-pressed={sel===b.name}>
            <span className="bh-avatar">{initials(b.label)}</span>
            <span className="bh-bot-text"><b>{b.label}</b><small className={'h-'+h.key}><i/>{h.label}</small></span>
            <span className="bh-count">{b.stats.records.toLocaleString('en-BD')}</span>
          </button>
          <Spark bot={b.name} daily={daily}/>
          {b.lastError&&<p className="bh-bot-err" title={b.lastError}><CircleAlert size={12}/>{b.lastError}</p>}
          <button className="bh-gear" onClick={()=>setModal({t:'settings',b})} aria-label={`${b.label} settings`}><Settings2 size={15}/></button>
        </div>})}
      </aside>

      <section className="bh-feed panel" aria-label="Activity">
        <div className="bh-filters">
          <div className="bh-search"><Search size={15}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search title, ID or data…" aria-label="Search records"/></div>
          <select value={kind} onChange={e=>setKind(e.target.value)} aria-label="Filter by type"><option value="">All types</option>{kinds.map(k=><option key={k.kind} value={k.kind}>{k.kind} ({k.n})</option>)}</select>
          <button className="bh-icon" onClick={refresh} aria-label="Refresh"><RefreshCw size={15}/></button>
        </div>
        {loading?<div className="bh-loading">Loading…</div>:!recs.length?<div className="bh-feed-empty"><b>{q||kind||sel?'No records match':'No records yet'}</b><p>{q||kind||sel?'Try a different search or clear the filters.':'Data from connected bots appears here as soon as it arrives.'}</p></div>:
        <div className="bh-table-wrap"><table className="bh-table"><thead><tr><th>When</th>{!sel&&<th>Bot</th>}<th>Record</th><th>Type</th><th className="r">Amount</th></tr></thead><tbody>
          {recs.map(r=><tr key={r.id} tabIndex={0} onClick={()=>setModal({t:'record',r})} onKeyDown={e=>{if(e.key==='Enter')setModal({t:'record',r})}}>
            <td className="t">{fmtTime(r.occurredAt)}</td>
            {!sel&&<td className="bot"><span className={'bh-chip k-'+(byName[r.bot]?.kind??'general')}>{byName[r.bot]?.label??r.bot}</span></td>}
            <td className="title"><b>{r.title}</b><small>{r.externalId}</small></td>
            <td className="type"><span className="badge">{r.kind}</span>{r.status&&<span className="bh-status">{r.status}</span>}</td>
            <td className="r amt">{r.amount!==null?<span className="bh-amt">{r.entryId&&<Check size={13} className="bh-led" aria-label="in ledger"/>}{money(r.amount)}</span>:'—'}</td>
          </tr>)}
        </tbody></table>
        {more&&<div className="bh-more"><button className="secondary" onClick={()=>loadRecs(true,recs[recs.length-1].occurredAt)}>Show older records</button></div>}</div>}
      </section>
    </div></>}

    <section id="bh-help" className="bh-help panel">
      <h2>How bot data gets here</h2>
      <div className="bh-help-grid">
        <div><h3>Live from the bot</h3><p>Each bot gets its own key. The bot sends a record whenever something happens — a payment, an order, a cleanup. If this app is unreachable, the bot keeps records in a queue and sends them later.</p></div>
        <div><h3>Old data from a file</h3><p>Use <b>Import data</b> with a CSV or JSON export. For a bot’s SQLite database, run <code>python nexa_sync.py import-sqlite bot.db payments</code> on the bot’s computer.</p></div>
        <div><h3>Never saved twice</h3><p>Every record carries the bot’s own ID. Sending or importing the same record again is skipped, so re-running an import is safe.</p></div>
      </div>
    </section>

    {modal?.t==='connect'&&<Modal title="Connect a bot" onClose={close} wide><ConnectWizard origin={origin} onClose={close} onDone={refresh}/></Modal>}
    {modal?.t==='import'&&<Modal title="Import bot data" onClose={close} wide><ImportPanel bots={bots} initial={sel} onClose={close} onDone={m=>{notify(m);refresh();onLedgerChange()}}/></Modal>}
    {modal?.t==='settings'&&<Modal title={`${modal.b.label} settings`} onClose={close} wide><BotSettings b={modal.b} origin={origin} onClose={close} onChanged={refresh} notify={notify}/></Modal>}
    {modal?.t==='record'&&<Modal title={modal.r.title} onClose={close}><RecordDrawer r={modal.r} bot={byName[modal.r.bot]} onClose={close} onDeleted={()=>{refresh();notify('Record deleted')}}/></Modal>}
  </div>;
}
