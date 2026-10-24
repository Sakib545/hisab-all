import { resolveBot, reconcile, json, errMsg } from '../../../../lib/bot-server';

const MAX_IDS = 50000;
// POST /api/bot/reconcile { kind: "expense", ids: [...every id the bot currently has...] }
export async function POST(req: Request) {
  let body: { bot?: unknown; kind?: unknown; ids?: unknown };
  try { body = await req.json(); } catch { return json({ error: 'invalid JSON' }, 400); }
  try {
    const bot = await resolveBot(req, body.bot);
    if (!bot) return json({ error: 'unauthorized' }, 401);
    const kind = String(body.kind ?? '').trim().toLowerCase();
    if (!/^[a-z0-9_-]{1,40}$/.test(kind)) throw Error('kind required');
    if (!Array.isArray(body.ids) || body.ids.length > MAX_IDS) throw Error(`ids: array of up to ${MAX_IDS}`);
    if (!body.ids.length) throw Error('ids is empty — refusing to remove everything. Send at least one id.');
    return json(await reconcile(bot, kind, body.ids as string[]));
  } catch (e) { return json({ error: errMsg(e) }, 400); }
}
