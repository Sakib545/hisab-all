import { sql, eq } from 'drizzle-orm';
import { getDb } from '../../../../db';
import { botRecords } from '../../../../db/schema';
import { resolveBot, ingest, touch, json, errMsg } from '../../../../lib/bot-server';

// GET /api/bot/ingest  → connection test (bot identity + how many records are stored)
export async function GET(req: Request) {
  try {
    const bot = await resolveBot(req, new URL(req.url).searchParams.get('bot'));
    if (!bot) return json({ error: 'unauthorized' }, 401);
    await touch(bot);
    const row = await getDb().select({ n: sql<number>`count(*)` }).from(botRecords).where(eq(botRecords.bot, bot)).get();
    return json({ ok: true, bot, synced: row?.n ?? 0 });
  } catch (e) { return json({ error: errMsg(e) }, 400); }
}

// POST /api/bot/ingest  { records: [ {id, title, kind, at, amount, status, data, ledger}, ... ] }
export async function POST(req: Request) {
  let body: { bot?: unknown; records?: unknown; upsert?: unknown };
  try { body = await req.json(); } catch { return json({ error: 'invalid JSON' }, 400); }
  try {
    const bot = await resolveBot(req, body.bot);
    if (!bot) return json({ error: 'unauthorized' }, 401);
    return json(await ingest(bot, body.records as never, body.upsert === true));
  } catch (e) { return json({ error: errMsg(e) }, 400); }
}
