// Port of BusinessExpenseBot/expense_parser.py — same rules as the Telegram bot.
export const EXPENSE_CATEGORIES = ['নারিকেল তেলের টাকা', 'স্টিকারের টাকা', 'বোতলের টাকা', 'তেলের টাকা', 'পলির টাকা', 'বক্সের টাকা', 'বেতন'];
export type ParsedExpense = { amount: number; category: string };

const bn = (s: string) => s.replace(/[০-৯]/g, d => String('০১২৩৪৫৬৭৮৯'.indexOf(d)));
export const normalize = (t: string) => bn(t).trim().replace(/\s+/g, ' ');
const AMOUNT_START = /(?:^|\s)৳?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s+/g;

function cleanCategory(v: string): string | null {
  let c = v.replace(/^[\s,;|:\-–—।.!?]+|[\s,;|:\-–—।.!?]+$/g, '').replace(/\s+/g, ' ');
  if (!c || c.length > 80 || !/[A-Za-z\u0980-\u09FF]/.test(c)) return null;
  return c;
}
function canonical(supplied: string, cats: string[]): string {
  const k = normalize(supplied).toLowerCase();
  return cats.find(c => normalize(c).toLowerCase() === k) ?? supplied;
}

/** "500 খাবার", "500 খরচ 300 খাবার", multi-line — returns [] if not understood. */
export function parseExpenses(text: string, cats = EXPENSE_CATEGORIES): ParsedExpense[] {
  const t = normalize(text);
  if (!t) return [];
  const matches = [...t.matchAll(AMOUNT_START)];
  if (!matches.length || t.slice(0, matches[0].index).trim()) return [];
  const out: ParsedExpense[] = [];
  for (let i = 0; i < matches.length; i++) {
    const m = matches[i];
    const end = i + 1 < matches.length ? matches[i + 1].index! : t.length;
    const cat = cleanCategory(t.slice(m.index! + m[0].length, end));
    if (!cat) return [];
    const amount = Number(m[1].replace(/,/g, ''));
    if (!(amount > 0)) return [];
    out.push({ amount, category: canonical(cat, cats) });
  }
  return out;
}

/** "500" or "৳১,২০০" alone → amount (then ask for category). */
export function parseAmountOnly(text: string): number | null {
  const m = normalize(text).match(/^৳?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)$/);
  if (!m) return null;
  const a = Number(m[1].replace(/,/g, ''));
  return a > 0 ? a : null;
}

// Week = Monday–Sunday, same as the bot's export.
export function weekRange(offset: number, today: string): [string, string] {
  const d = new Date(today + 'T00:00:00Z');
  const monday = new Date(d.getTime() - ((d.getUTCDay() + 6) % 7) * 864e5 - offset * 7 * 864e5);
  const sunday = new Date(monday.getTime() + 6 * 864e5);
  return [monday.toISOString().slice(0, 10), sunday.toISOString().slice(0, 10)];
}
export function monthRange(offset: number, today: string): [string, string] {
  const [y, m] = today.split('-').map(Number);
  const idx = y * 12 + (m - 1) - offset, yy = Math.floor(idx / 12), mm = idx % 12 + 1;
  const last = new Date(Date.UTC(yy, mm, 0)).getUTCDate();
  const p = (n: number) => String(n).padStart(2, '0');
  return [`${yy}-${p(mm)}-01`, `${yy}-${p(mm)}-${p(last)}`];
}

/** Category totals: configured categories first (bot order), then custom ones A–Z. */
export function categoryTotals(rows: { category: string; amount: number }[], cats = EXPENSE_CATEGORIES) {
  const t = new Map<string, number>();
  for (const r of rows) t.set(r.category, (t.get(r.category) ?? 0) + r.amount);
  const known = cats.filter(c => t.get(c)).map(c => ({ category: c, amount: t.get(c)!, custom: false }));
  const custom = [...t.keys()].filter(c => !cats.includes(c)).sort((a, b) => a.localeCompare(b)).map(c => ({ category: c, amount: t.get(c)!, custom: true }));
  return [...known, ...custom];
}
