'use client';
import {useMemo} from 'react';
import {Download,FileText} from 'lucide-react';
import {useBotData,Stats,downloadCsv,printReport,tkf,monthLabel,Notice} from './bot-kit';
import {settlement,orderDay,type Rec,type OrderData,type TxData} from '../lib/buraq';

type Entry={type:string;amount:number;date:string;reference:string;category:string};

/** Same as the bots' Central Export "Combined Summary", live from all three bots. */
export default function BuraqCentral({rows,go}:{rows:Entry[];go:(tab:string)=>void}){
  const {recs,loading,error}=useBotData(['order','bank_tx']);
  const orders=(recs.order??[]) as Rec<OrderData>[], txs=(recs.bank_tx??[]) as Rec<TxData>[];
  const bankBots=new Set(txs.map(t=>t.bot));
  // business expenses = every ledger expense except receipts the bank bot itself copied into the ledger
  const expenses=rows.filter(r=>r.type==='expense'&&![...bankBots].some(b=>r.reference?.startsWith(`tg:${b}:`)));
  const table=useMemo(()=>{
    const months=new Set<string>();
    orders.forEach(o=>months.add(orderDay(o).slice(0,7)));txs.forEach(t=>months.add((t.d.payment_month||t.d.date||'').slice(0,7)));expenses.forEach(e=>months.add(e.date.slice(0,7)));
    return [...months].filter(m=>/^\d{4}-\d{2}$/.test(m)).sort().reverse().map(m=>{
      const s=settlement(orders.filter(o=>orderDay(o).slice(0,7)===m));
      const dollar=txs.filter(t=>(t.d.payment_month||t.d.date||'').slice(0,7)===m).reduce((a,t)=>a+(t.a??0)/100,0);
      const exp=expenses.filter(e=>e.date.slice(0,7)===m).reduce((a,e)=>a+e.amount/100,0);
      return {m,expected:s.expected_settlement,payout:s.matched_payout,remaining:s.remaining,dollar,exp,balance:s.matched_payout-dollar-exp};
    });
  },[orders,txs,expenses]);
  const sum=(k:'expected'|'payout'|'dollar'|'exp'|'balance'|'remaining')=>table.reduce((a,r)=>a+r[k],0);
  if(loading)return <div className="bh-loading">Loading…</div>;
  return <div className="bh bk">
    <div className="title-row"><div><h1>BURAQ Central</h1><p className="subtitle">Courier settlement, Dollar payment আর ব্যবসার খরচ — তিন bot মিলিয়ে এক হিসাব।</p></div>
      <div className="bh-head-actions">
        <button className="secondary" onClick={()=>downloadCsv('BURAQ-Central',['Month','Expected Courier Settlement','Courier Payout','Courier Remaining','Dollar Payment','Business Expense','Balance after expenses'],table.map(r=>[r.m,r.expected,r.payout,r.remaining,r.dollar,r.exp,r.balance]))}><Download size={16}/>CSV</button>
        <button className="secondary" onClick={()=>printReport('BURAQ CENTRAL ACCOUNTS','Combined Summary',[{headers:['খাত','টাকা'],right:[1],rows:[['Expected Courier Settlement',tkf(sum('expected'))],['Courier Payout',tkf(sum('payout'))],['Dollar Payment',tkf(sum('dollar'))],['Business Expense',tkf(sum('exp'))]],foot:['Balance after expenses',tkf(sum('balance'))]},{h:'মাসভিত্তিক',headers:['মাস','Expected','Payout','Dollar','Expense','Balance'],right:[1,2,3,4,5],rows:table.map(r=>[monthLabel(r.m),tkf(r.expected),tkf(r.payout),tkf(r.dollar),tkf(r.exp),tkf(r.balance)])}])}><FileText size={16}/>PDF</button></div></div>
    {error&&<Notice kind="error">{error}</Notice>}
    <Stats items={[['Expected courier settlement',tkf(sum('expected')),<>বাকি {tkf(sum('remaining'))}</>],['Courier payout',tkf(sum('payout')),'Paid Invoice থেকে'],['Dollar payment',tkf(sum('dollar')),`${txs.length}টি receipt`],['ব্যবসার খরচ',tkf(sum('exp')),`${expenses.length}টি খরচ`]]}/>
    <section className={'panel bk-balance'+(sum('balance')<0?' neg':'')}><span>Balance after expenses</span><b>{tkf(sum('balance'))}</b><small>Courier payout − Dollar payment − ব্যবসার খরচ</small></section>
    <section className="panel xb-list"><div className="bh-table-wrap"><table className="bh-table"><thead><tr><th>মাস</th><th className="r">Expected</th><th className="r">Payout</th><th className="r">বাকি</th><th className="r">Dollar</th><th className="r">খরচ</th><th className="r">Balance</th></tr></thead><tbody>
      {table.map(r=><tr key={r.m} className="static"><td className="title"><b>{monthLabel(r.m)}</b></td><td className="r">{tkf(r.expected)}</td><td className="r">{tkf(r.payout)}</td><td className="r t">{tkf(r.remaining)}</td><td className="r">{tkf(r.dollar)}</td><td className="r">{tkf(r.exp)}</td><td className={'r amt'+(r.balance<0?' neg':'')}>{tkf(r.balance)}</td></tr>)}
    </tbody></table></div>{!table.length&&<p className="xb-none">এখনো কোনো data নেই।</p>}</section>
    <div className="bk-links"><button className="link" onClick={()=>go('Courier & COD')}>Courier & COD →</button><button className="link" onClick={()=>go('Dollar payments')}>Dollar payments →</button><button className="link" onClick={()=>go('খরচের খাতা')}>খরচের খাতা →</button></div>
    <p className="bk-note">মাস: courier — order-এর তারিখ; dollar — payment-এর হিসাবের মাস; খরচ — খরচের তারিখ। Bank receipt যদি ledger-এও যায় (NEXA_LEDGER=expense), সেটা খরচে দুবার গোনা হয় না।</p>
  </div>;
}
