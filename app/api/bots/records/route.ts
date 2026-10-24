import { and, eq, like, lt, or, desc, sql } from 'drizzle-orm';
import { getDb } from '../../../../db';
import { bots, botRecords } from '../../../../db/schema';
import { cleanBotName } from '../../../../lib/bot-sync';
import { ingest, json, errMsg } from '../../../../lib/bot-server';

// GET ?bot=&kind=&q=&before=&limit=  → newest first
export async function GET(req: Request) {
  try {
    const u = new URL(req.url), p = u.searchParams;
    const limit = Math.min(Math.max(Number(p.get('limit')) || 50, 1), 200);
    const conds = [];
    if (p.get('bot')) conds.push(eq(botRecords.bot, p.get('bot')!));
    if (p.get('kind')) conds.push(eq(botRecords.kind, p.get('kind')!));
    if (p.get('before')) conds.push(lt(botRecords.occurredAt, p.get('before')!));
    const q = p.get('q')?.trim();
    if (q) conds.push(or(like(botRecords.title, `%${q}%`), like(botRecords.externalId, `%${q}%`), like(botRecords.data, `%${q}%`)));
    const where = conds.length ? and(...conds) : undefined;
    const db = getDb();
    const rows = await db.select().from(botRecords).where(where).orderBy(desc(botRecords.occurredAt)).limit(limit + 1);
    const kinds = await db.select({ kind: botRecords.kind, n: sql<number>`count(*)` }).from(botRecords).groupBy(botRecords.kind);
    return json({ records: rows.slice(0, limit), more: rows.length > limit, kinds });
  } catch (e) { return json({ error: 'Records লোড হয়নি।', detail: errMsg(e) }, 500); }
}

// POST {bot, records}  → import from the app (CSV / JSON file). Same rules as live sync, duplicates skipped.
export async function POST(req: Request) {
  try {
    const p = await req.json() as { bot?: string; records?: unknown };
    const name = cleanBotName(p.bot);
    const exists = await getDb().select({ id: bots.id }).from(bots).where(eq(bots.name, name)).get();
    if (!exists) throw Error('আগে bot যোগ করুন, তারপর import করুন।');
    return json(await ingest(name, p.records as never));
  } catch (e) { return json({ error: errMsg(e) }, 400); }
}

// DELETE ?id=  → remove one record (linked ledger entry stays; delete it from Transactions if needed)
export async function DELETE(req: Request) {
  const id = new URL(req.url).searchParams.get('id');
  if (!id) return json({ error: 'id missing' }, 400);
  try { await getDb().delete(botRecords).where(eq(botRecords.id, id)); return json({ ok: true }); }
  catch (e) { return json({ error: errMsg(e) }, 500); }
}
