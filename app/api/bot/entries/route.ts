// Legacy endpoint (ledger-only format). New bots should use /api/bot/ingest.
import { entryToRecord, type BotEntryInput, type BotRecordInput } from '../../../../lib/bot-sync';
import { resolveBot, ingest, json, errMsg } from '../../../../lib/bot-server';
export { GET } from '../ingest/route';

export async function POST(req: Request) {
  let body: { bot?: unknown; entries?: unknown };
  try { body = await req.json(); } catch { return json({ error: 'invalid JSON' }, 400); }
  try {
    const bot = await resolveBot(req, body.bot);
    if (!bot) return json({ error: 'unauthorized' }, 401);
    const list = Array.isArray(body.entries) ? body.entries as BotEntryInput[] : [];
    const records = list.map(e => { try { return entryToRecord(e); } catch { return { id: e?.id, ledger: { type: '__invalid' } } as BotRecordInput; } });
    return json(await ingest(bot, records));
  } catch (e) { return json({ error: errMsg(e) }, 400); }
}
