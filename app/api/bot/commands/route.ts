import { resolveBot, claimCommands, finishCommand, json, errMsg } from '../../../../lib/bot-server';

// Bot side. GET → claim up to 3 pending commands. POST {id, ok, result} → report the outcome.
export async function GET(req: Request) {
  try {
    const bot = await resolveBot(req, new URL(req.url).searchParams.get('bot'));
    if (!bot) return json({ error: 'unauthorized' }, 401);
    return json({ ok: true, commands: await claimCommands(bot) });
  } catch (e) { return json({ error: errMsg(e) }, 400); }
}
export async function POST(req: Request) {
  let body: { bot?: unknown; id?: unknown; ok?: unknown; result?: unknown };
  try { body = await req.json(); } catch { return json({ error: 'invalid JSON' }, 400); }
  try {
    const bot = await resolveBot(req, body.bot);
    if (!bot) return json({ error: 'unauthorized' }, 401);
    if (!(await finishCommand(bot, String(body.id ?? ''), body.ok === true, body.result))) throw Error('command not found');
    return json({ ok: true });
  } catch (e) { return json({ error: errMsg(e) }, 400); }
}
