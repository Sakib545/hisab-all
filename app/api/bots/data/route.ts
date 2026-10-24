// All records of some kinds (for the module pages). Compact rows; data JSON parsed.
import { and, eq, inArray, desc } from 'drizzle-orm';
import { getDb } from '../../../../db';
import { botRecords } from '../../../../db/schema';
import { json, errMsg } from '../../../../lib/bot-server';

const LIMIT = 40000;
export async function GET(req: Request) {
  try {
    const u = new URL(req.url);
    const kinds = (u.searchParams.get('kinds') ?? '').split(',').map(s => s.trim()).filter(Boolean).slice(0, 10);
    if (!kinds.length) throw Error('kinds required');
    const bot = u.searchParams.get('bot');
    const where = bot ? and(eq(botRecords.bot, bot), inArray(botRecords.kind, kinds)) : inArray(botRecords.kind, kinds);
    const rows = await getDb().select({ bot: botRecords.bot, kind: botRecords.kind, id: botRecords.externalId, t: botRecords.title, a: botRecords.amount, s: botRecords.status, at: botRecords.occurredAt, d: botRecords.data, r: botRecords.receivedAt })
      .from(botRecords).where(where).orderBy(desc(botRecords.occurredAt)).limit(LIMIT + 1);
    const out: Record<string, unknown[]> = Object.fromEntries(kinds.map(k => [k, []]));
    for (const r of rows.slice(0, LIMIT)) {
      let d: unknown = {}; try { d = JSON.parse(r.d); } catch {}
      out[r.kind].push({ bot: r.bot, id: r.id, t: r.t, a: r.a, s: r.s, at: r.at, d, r: r.r });
    }
    return json({ records: out, truncated: rows.length > LIMIT });
  } catch (e) { return json({ error: errMsg(e) }, 400); }
}
