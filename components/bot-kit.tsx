'use client';
import {useState,useEffect,useCallback,useRef} from 'react';
import {Check,CircleAlert,Loader2,FileUp,X,Clock3} from 'lucide-react';
import type {Rec} from '../lib/buraq';

export const tkf=(taka:number|null|undefined)=>{const v=taka??0;return (v<0?'−':'')+'৳'+Math.abs(v).toLocaleString('en-BD',{maximumFractionDigits:2})};
export const tk=(paisa:number|null|undefined)=>tkf((paisa??0)/100);
export const num=(n:number)=>n.toLocaleString('en-BD');
export const fmtDate=(iso:string)=>iso?new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Dhaka',day:'numeric',month:'short',year:'numeric'}).format(new Date(iso)):'—';
export const fmtDT=(iso:string)=>iso?new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Dhaka',day:'numeric',month:'short',hour:'numeric',minute:'2-digit'}).format(new Date(iso)):'—';
const BN_M=['জানুয়ারি','ফেব্রুয়ারি','মার্চ','এপ্রিল','মে','জুন','জুলাই','আগস্ট','সেপ্টেম্বর','অক্টোবর','নভেম্বর','ডিসেম্বর'];
export const monthLabel=(ym:string)=>/^\d{4}-\d{2}$/.test(ym)?`${BN_M[Number(ym.slice(5))-1]} ${ym.slice(0,4)}`:ym||'—';
async function api<T>(url:string,init?:RequestInit):Promise<T>{const r=await fetch(url,init?{...init,headers:{'Content-Type':'application/json'}}:undefined);const d=await r.json() as T&{error?:string};if(!r.ok)throw Error(d.error||'Request failed');return d}

/** All records of some kinds, plus which bot they come from. */
export function useBotData(kinds:string[]){
  const [recs,setRecs]=useState<Record<string,Rec[]>>({}),[loading,setLoading]=useState(true),[error,setError]=useState(''),[bots,setBots]=useState<{name:string;label:string;lastSeenAt:string|null}[]>([]);
  const key=kinds.join(',');
  const reload=useCallback(async()=>{try{const [d,b]=await Promise.all([api<{records:Record<string,Rec[]>}>(`/api/bots/data?kinds=${key}`),api<{bots:{name:string;label:string;lastSeenAt:string|null}[]}>('/api/bots')]);setRecs(d.records);setBots(b.bots);setError('')}catch(e){setError(String(e).replace(/^Error: /,''))}finally{setLoading(false)}},[key]);
  useEffect(()=>{reload()},[reload]);
  useEffect(()=>{const t=setInterval(()=>{if(document.visibilityState==='visible')reload()},45000);return()=>clearInterval(t)},[reload]);
  const bot=Object.values(recs).flat()[0]?.bot??'';
  const botInfo=bots.find(b=>b.name===bot);
  return {recs,loading,error,reload,bot,botInfo,bots};
}

export type Cmd={id:string;action:string;payload:Record<string,any>;fileName:string|null;status:'pending'|'running'|'done'|'failed';result:any;createdAt:string;doneAt:string|null};

/** Phone photos are often 2–5 MB. Re-encode as JPEG (long side ≤ 2200 px) so they fit the upload limit; OCR quality stays the same. */
export async function shrinkImage(file:File,maxSide=2200,quality=0.86):Promise<File>{
  try{
    const bmp=await createImageBitmap(file);
    const scale=Math.min(1,maxSide/Math.max(bmp.width,bmp.height));
    const c=document.createElement('canvas');c.width=Math.round(bmp.width*scale);c.height=Math.round(bmp.height*scale);
    const ctx=c.getContext('2d')!;ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(bmp,0,0,c.width,c.height);
    for(const q of [quality,0.75,0.65]){
      const blob=await new Promise<Blob|null>(r=>c.toBlob(r,'image/jpeg',q));
      if(blob&&blob.size<=1_300_000)return new File([blob],file.name.replace(/\.\w+$/,'')+'.jpg',{type:'image/jpeg'});
    }
  }catch{}
  return file;
}

/** Send work to the bot and follow it until it is done. */
export function useCommands(bot:string,onDone:()=>void){
  const [list,setList]=useState<Cmd[]>([]);
  const watching=useRef(new Set<string>());
  const load=useCallback(async()=>{if(!bot)return;try{const d=await api<{commands:Cmd[]}>(`/api/bots/commands?bot=${bot}`);setList(d.commands)}catch{}},[bot]);
  useEffect(()=>{load()},[load]);
  useEffect(()=>{const t=setInterval(async()=>{if(!watching.current.size)return;const ids=[...watching.current];try{const d=await api<{commands:Cmd[]}>(`/api/bots/commands?ids=${ids.join(',')}`);let finished=false;
    setList(l=>{const m=new Map(l.map(c=>[c.id,c]));d.commands.forEach(c=>m.set(c.id,c));return [...m.values()].sort((a,b)=>b.createdAt.localeCompare(a.createdAt))});
    d.commands.forEach(c=>{if(c.status==='done'||c.status==='failed'){watching.current.delete(c.id);finished=true}});if(finished)onDone()}catch{}},2500);return()=>clearInterval(t)},[onDone]);
  const run=useCallback(async(action:string,payload:Record<string,any>={},inFile?:File)=>{
    let file=inFile;
    let fileData:string|undefined;
    if(file&&/^image\//.test(file.type)&&file.size>700_000)file=await shrinkImage(file);
    if(file){if(file.size>1_400_000)throw Error(`${file.name} অনেক বড় (সর্বোচ্চ 1.4 MB)। বড় file সরাসরি Telegram bot-এ পাঠান।`);fileData=await new Promise<string>((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=()=>rej(Error('File পড়া যায়নি'));r.readAsDataURL(file)})}
    const d=await api<{id:string}>('/api/bots/commands',{method:'POST',body:JSON.stringify({bot,action,payload,fileName:file?.name,fileData})});
    watching.current.add(d.id);
    setList(l=>[{id:d.id,action,payload,fileName:file?.name??null,status:'pending',result:null,createdAt:new Date().toISOString(),doneAt:null},...l]);
    return d.id;
  },[bot]);
  const cancel=useCallback(async(id:string)=>{const r=await fetch(`/api/bots/commands?id=${id}`,{method:'DELETE'});if(r.ok){watching.current.delete(id);setList(l=>l.filter(c=>c.id!==id))}},[]);
  const busy=list.some(c=>c.status==='pending'||c.status==='running');
  return {list,run,busy,cancel,reload:load};
}

export function CmdStatus({c}:{c:Cmd}){
  return c.status==='done'?<span className="bk-st done"><Check size={13}/>হয়েছে</span>:c.status==='failed'?<span className="bk-st failed"><CircleAlert size={13}/>হয়নি</span>:c.status==='running'?<span className="bk-st run"><Loader2 size={13} className="spin"/>Bot কাজ করছে</span>:<span className="bk-st wait"><Clock3 size={13}/>Bot-এর অপেক্ষায়</span>;
}

/** Recent actions sent to the bot, with a human summary of each result. */
export function CommandLog({list,labels,describe,cancel,lastSeen}:{list:Cmd[];labels:Record<string,string>;describe:(c:Cmd)=>React.ReactNode;cancel:(id:string)=>void;lastSeen?:string|null}){
  if(!list.length)return null;
  const stale=lastSeen?Date.now()-Date.parse(lastSeen)>120000:true;
  return <section className="panel bk-log" aria-label="Bot-এ পাঠানো কাজ">
    <div className="bk-log-head"><h3>Bot-এ পাঠানো কাজ</h3>{list.some(c=>c.status==='pending')&&stale&&<span className="bk-warn"><CircleAlert size={13}/>Bot অনেকক্ষণ সাড়া দেয়নি — bot চালু আছে আর Nexa patch বসানো হয়েছে কিনা দেখুন।</span>}</div>
    <ul>{list.slice(0,8).map(c=><li key={c.id} className={c.status}>
      <div className="bk-log-main"><b>{labels[c.action]??c.action}</b>{c.fileName&&<small>{c.fileName}</small>}<span className="bk-time">{fmtDT(c.createdAt)}</span></div>
      <div className="bk-log-res"><CmdStatus c={c}/>{c.status==='failed'?<span className="bk-err">{String(c.result?.error??'').replace(/^\w+Error: /,'')}</span>:c.status==='done'?<span>{describe(c)}</span>:null}{c.status==='pending'&&<button className="link" onClick={()=>cancel(c.id)}>বাতিল</button>}</div>
    </li>)}</ul>
  </section>;
}

export function FileDrop({accept,label,hint,multiple,onFiles,disabled}:{accept:string;label:string;hint:string;multiple?:boolean;onFiles:(f:File[])=>void;disabled?:boolean}){
  const [over,setOver]=useState(false);
  return <label className={'bh-drop bk-drop'+(over?' over':'')+(disabled?' off':'')} onDragOver={e=>{e.preventDefault();setOver(true)}} onDragLeave={()=>setOver(false)} onDrop={e=>{e.preventDefault();setOver(false);if(!disabled&&e.dataTransfer.files.length)onFiles([...e.dataTransfer.files])}}>
    <FileUp size={22}/><b>{label}</b><small>{hint}</small>
    <input type="file" accept={accept} multiple={multiple} disabled={disabled} onChange={e=>{if(e.target.files?.length)onFiles([...e.target.files]);e.target.value=''}}/>
  </label>;
}

export function Tabs<T extends string>({tabs,value,onChange}:{tabs:[T,string,number?][];value:T;onChange:(t:T)=>void}){
  return <div className="bk-tabs" role="tablist">{tabs.map(([k,l,n])=><button key={k} role="tab" aria-selected={value===k} className={value===k?'on':''} onClick={()=>onChange(k)}>{l}{n!==undefined&&<span>{num(n)}</span>}</button>)}</div>;
}

export function Stats({items}:{items:[string,React.ReactNode,React.ReactNode?][]}){
  return <section className="bh-summary bk-stats" style={{'--n':Math.min(items.length,4)} as React.CSSProperties}>{items.map(([l,v,s],i)=><div key={i}><span>{l}</span><b>{v}</b>{s&&<small>{s}</small>}</div>)}</section>;
}

export function downloadCsv(name:string,headers:string[],rows:(string|number|null|undefined)[][]){
  const esc=(v:unknown)=>{const s=String(v??'');return /[",\n\r]/.test(s)?`"${s.replace(/"/g,'""')}"`:s};
  const blob=new Blob(['\uFEFF'+[headers,...rows].map(r=>r.map(esc).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name.replace(/[^\w\u0980-\u09FF.-]+/g,'-')+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);
}
export function printReport(title:string,sub:string,sections:{h?:string;headers:string[];rows:(string|number)[][];foot?:(string|number)[];right?:number[]}[]){
  const w=window.open('','_blank');if(!w)return;
  const e=(s:unknown)=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]!));
  const tbl=(s:typeof sections[0])=>`${s.h?`<h2>${e(s.h)}</h2>`:''}<table><thead><tr>${s.headers.map((h,i)=>`<th${s.right?.includes(i)?' class=r':''}>${e(h)}</th>`).join('')}</tr></thead><tbody>${s.rows.map(r=>`<tr>${r.map((c,i)=>`<td${s.right?.includes(i)?' class=r':''}>${e(c)}</td>`).join('')}</tr>`).join('')}</tbody>${s.foot?`<tfoot><tr>${s.foot.map((c,i)=>`<td${s.right?.includes(i)?' class=r':''}>${e(c)}</td>`).join('')}</tr></tfoot>`:''}</table>`;
  w.document.write(`<!doctype html><html lang="bn"><meta charset="utf-8"><title>${e(title)}</title><style>body{font-family:"Noto Sans Bengali","Hind Siliguri",Inter,Arial,sans-serif;color:#1d2a24;margin:30px}h1{font-size:20px;margin:0}p{color:#6b756f;margin:4px 0 18px;font-size:12px}h2{font-size:14px;margin:18px 0 8px}table{width:100%;border-collapse:collapse;font-size:11.5px}th{background:#17324d;color:#fff;text-align:left;padding:6px 8px}td{padding:5px 8px;border:1px solid #dfe5e1}.r{text-align:right}tfoot td{font-weight:700;background:#eaf2f8}@media print{body{margin:10mm}}</style><h1>${e(title)}</h1><p>${e(sub)} · Nexa Hisab · ${new Date().toLocaleString('en-GB',{timeZone:'Asia/Dhaka'})}</p>${sections.map(tbl).join('')}<script>onload=()=>setTimeout(()=>print(),300)<\/script></html>`);
  w.document.close();
}

export function Confirm({text,yes,onYes,onNo,danger}:{text:React.ReactNode;yes:string;onYes:()=>void;onNo:()=>void;danger?:boolean}){
  return <div className="bh-confirm bk-confirm"><p>{text}</p><div className="bh-actions left"><button className="secondary" onClick={onNo}>না</button><button className={danger?'danger solid':'primary'} onClick={onYes}>{yes}</button></div></div>;
}

export function EmptyBot({name,hint,onGo}:{name:string;hint:string;onGo:()=>void}){
  return <section className="bh-empty"><div className="bh-empty-art" aria-hidden><FileUp size={30}/></div><div><h2>{name} এখনো connect হয়নি</h2><p>{hint}</p><div className="bh-actions left"><button className="primary" onClick={onGo}>Telegram bots page-এ যান</button></div></div></section>;
}

export function Notice({kind='info',children,onClose}:{kind?:'info'|'warn'|'error';children:React.ReactNode;onClose?:()=>void}){
  return <div className={`bk-notice ${kind}`} role={kind==='error'?'alert':'status'}>{kind!=='info'&&<CircleAlert size={15}/>}<div>{children}</div>{onClose&&<button onClick={onClose} aria-label="Close"><X size={14}/></button>}</div>;
}
