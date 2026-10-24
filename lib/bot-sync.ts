// Pure helpers for Telegram bot → Nexa Hisab sync (shared by API routes, UI and tests).
export const BOT_TYPES = ['income', 'expense', 'receivable', 'payable'] as const;
export const BOT_KINDS = ['finance', 'orders', 'general'] as const;
export const MAX_BATCH = 100;
const MAX_DATA = 16000;

export type BotEntryInput = {
  id: string; type: string; amount: number | string; date: string;
  category?: string; party?: string; account?: string; note?: string;
};
export type LedgerInput = { type: string; category?: string; account?: string; party?: string; note?: string };
export type BotRecordInput = {
  id: string | number; title?: string; kind?: string; at?: string;
  amount?: number | string | null; status?: string;
  data?: Record<string, unknown>; ledger?: LedgerInput | null; hash?: string;
};
export type CleanEntry = { date: string; type: string; amount: number; category: string; party: string; account: string; reference: string; note: string };
export type CleanRecord = {
  externalId: string; kind: string; title: string; amount: number | null; status: string;
  data: string; occurredAt: string; entry: CleanEntry | null; hash: string;
};

/** Two 32-bit FNV-1a passes (different seeds) as 16 hex chars — fast change detection, not security. */
export function fnv1a(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let a = 0x811c9dc5, b = 0x01000193 ^ 0x5bd1e995;
  for (const x of bytes) { a = Math.imul(a ^ x, 0x01000193); b = Math.imul(b ^ x, 0x01000193) ^ (b >>> 13); }
  return (a >>> 0).toString(16).padStart(8, '0') + (b >>> 0).toString(16).padStart(8, '0');
}
const cut = (x: unknown, max: number) => String(x ?? '').trim().slice(0, max);
const bnDigits = (s: string) => s.replace(/[০-৯]/g, d => String('০১২৩৪৫৬৭৮৯'.indexOf(d)));

export function cleanBotName(x: unknown): string {
  const b = String(x ?? '').trim().toLowerCase();
  if (!/^[a-z0-9_-]{2,40}$/.test(b)) throw Error('bot name: 2-40 chars, a-z 0-9 _ -');
  return b;
}
export function slugify(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
}
export function botReference(bot: string, id: unknown): string {
  const i = cut(id, 150);
  if (!i) throw Error('id missing');
  return `tg:${bot}:${i}`;
}
export function toPaisa(amount: unknown): number {
  const s = bnDigits(String(amount ?? '')).replace(/[,\s৳]/g, '').replace(/^(tk|bdt)/i, '');
  if (!/^\d+(\.\d{1,2})?$/.test(s)) throw Error('amount invalid');
  const p = Math.round(Number(s) * 100);
  if (!Number.isSafeInteger(p) || p <= 0 || p > 100000000000) throw Error('amount out of range');
  return p;
}

// Accepts YYYY-MM-DD, DD/MM/YYYY, ISO datetime or unix seconds/ms → ISO string (UTC).
export function toIso(at: unknown, now = new Date()): string {
  if (at === undefined || at === null || at === '') return now.toISOString();
  const s = bnDigits(String(at).trim());
  if (/^\d{10}(\d{3})?$/.test(s)) return new Date(Number(s) * (s.length === 10 ? 1000 : 1)).toISOString();
  let m = s.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
  if (m) return new Date(`${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}T06:00:00Z`).toISOString();
  m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  // No timezone given → treat as Bangladesh time (UTC+6), which is what local bots store.
  const naive = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s);
  const d = new Date(m ? `${s}T06:00:00Z` : naive ? s.replace(' ', 'T') + '+06:00' : s);
  if (isNaN(d.getTime())) throw Error('date/time invalid');
  return d.toISOString();
}
export const dhakaDate = (iso: string) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Dhaka' }).format(new Date(iso));

export function cleanRecord(bot: string, r: BotRecordInput, now = new Date()): CleanRecord {
  if (!r || typeof r !== 'object') throw Error('record must be an object');
  const externalId = cut(r.id, 150);
  if (!externalId) throw Error('id missing');
  const amount = r.amount === undefined || r.amount === null || r.amount === '' ? null : toPaisa(r.amount);
  const occurredAt = toIso(r.at, now);
  const data = JSON.stringify(r.data && typeof r.data === 'object' ? r.data : {});
  if (data.length > MAX_DATA) throw Error(`data too large (max ${MAX_DATA} chars)`);
  let entry: CleanEntry | null = null;
  if (r.ledger) {
    const l = r.ledger;
    if (!(BOT_TYPES as readonly string[]).includes(l.type)) throw Error('ledger.type must be income/expense/receivable/payable');
    if (amount === null) throw Error('ledger record needs amount');
    entry = {
      date: dhakaDate(occurredAt), type: l.type, amount,
      category: cut(l.category, 100) || (l.type === 'expense' ? 'Bank transfer' : 'Other'),
      party: cut(l.party, 200), account: cut(l.account, 100) || 'Cash',
      reference: botReference(bot, externalId), note: cut(l.note, 2000),
    };
  }
  const title = cut(r.title, 200) || entry?.party || entry?.category || externalId;
  const kind = cut(r.kind, 40).toLowerCase() || (entry ? 'payment' : 'event');
  // hash lets the server skip unchanged records and update changed ones (status changes etc.)
  const hash = cut(r.hash, 80) || fnv1a(`${kind}|${title}|${amount}|${cut(r.status, 40)}|${occurredAt}|${data}|${entry ? JSON.stringify(entry) : ''}`);
  return { externalId, kind, title, amount, status: cut(r.status, 40), data, occurredAt, entry, hash };
}

// Legacy /api/bot/entries format → record.
export function entryToRecord(e: BotEntryInput): BotRecordInput {
  if (!(BOT_TYPES as readonly string[]).includes(e?.type)) throw Error('type must be income/expense/receivable/payable');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(e.date)) || isNaN(Date.parse(e.date))) throw Error('date must be YYYY-MM-DD');
  return { id: e.id, at: e.date, amount: e.amount, kind: 'payment', title: e.party || e.category,
    ledger: { type: e.type, category: e.category, account: e.account, party: e.party, note: e.note } };
}
export function cleanBotEntry(bot: string, e: BotEntryInput): CleanEntry {
  const r = cleanRecord(bot, entryToRecord(e));
  return r.entry as CleanEntry;
}

export function tokenMatches(given: string | null, expected: string | undefined): boolean {
  if (!expected || expected.length < 24 || !given) return false;
  const a = new TextEncoder().encode(given), b = new TextEncoder().encode(expected);
  let diff = a.length ^ b.length;
  for (let i = 0; i < b.length; i++) diff |= (a[i] ?? 0) ^ b[i];
  return diff === 0;
}
export async function sha256Hex(s: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}
export function newToken(): string {
  const b = new Uint8Array(24); crypto.getRandomValues(b);
  return 'nxh_' + [...b].map(x => x.toString(16).padStart(2, '0')).join('');
}

// ---- CSV import (browser) -------------------------------------------------
export function parseCsv(text: string): string[][] {
  const rows: string[][] = []; let row: string[] = [], cell = '', q = false;
  const t = text.replace(/^\uFEFF/, '');
  const sep = (t.split('\n')[0].match(/;/g)?.length ?? 0) > (t.split('\n')[0].match(/,/g)?.length ?? 0) ? ';' : ',';
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (q) { if (c === '"' && t[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') q = false; else cell += c; }
    else if (c === '"') q = true;
    else if (c === sep) { row.push(cell); cell = ''; }
    else if (c === '\n' || c === '\r') { if (c === '\r' && t[i + 1] === '\n') i++; row.push(cell); cell = ''; if (row.some(x => x.trim())) rows.push(row); row = []; }
    else cell += c;
  }
  row.push(cell); if (row.some(x => x.trim())) rows.push(row);
  return rows;
}
export type ColumnMap = { id: string; at: string; amount: string; title: string; status: string };
const GUESS: Record<keyof ColumnMap, RegExp> = {
  id: /^(id|_id|uid|ref|reference|row.?id)$|txn|trx|transaction.?id|receipt.?(id|no)|order.?(id|no)|invoice.?(id|no)/i,
  at: /(date|time|created|timestamp|তারিখ)/i,
  amount: /(amount|total|taka|tk|bdt|price|টাকা|পরিমাণ)/i,
  title: /(name|title|receiver|party|customer|description|details|purpose)/i,
  status: /(status|state)/i,
};
export function guessMapping(headers: string[]): ColumnMap {
  const m = { id: '', at: '', amount: '', title: '', status: '' } as ColumnMap;
  for (const k of Object.keys(GUESS) as (keyof ColumnMap)[]) m[k] = headers.find(h => GUESS[k].test(h.trim()) && !Object.values(m).includes(h)) ?? '';
  return m;
}
