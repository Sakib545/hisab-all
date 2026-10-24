// App side: queue an action for a bot (it runs it with its own code) and watch the result.
import { and, desc, eq, inArray } from 'drizzle-orm';
import { getDb } from '../../../../db';
import { bots, botCommands } from '../../../../db/schema';
import { json, errMsg } from '../../../../lib/bot-server';

const MAX_FILE_B64 = 1_900_000; // D1 rows are capped at 2 MB → ~1.4 MB file

export async function POST(req: Request) {
  try {
    const p = await req.json() as { bot?: string; action?: string; payload?: unknown; fileName?: string; fileData?: string };
    const bot = String(p.bot ?? ''), action = String(p.action ?? '');
    if (!/^[a-z0-9_]{2,40}$/.test(action)) throw Error('action invalid');
    const db = getDb();
    if (!(await db.select({ id: bots.id }).from(bots).where(eq(bots.name, bot)).get())) throw Error('Bot পাওয়া যায়নি।');
    if (p.fileData && p.fileData.length > MAX_FILE_B64) throw Error('File অনেক বড় (সর্বোচ্চ ~1.4 MB)। বড় file সরাসরি Telegram bot-এ পাঠান।');
    const payload = JSON.stringify(p.payload ?? {});
    if (payload.length > 20000) throw Error('payload too large');
    const id = crypto.randomUUID();
    await db.insert(botCommands).values({ id, bot, action, payload, fileName: p.fileName?.slice(0, 200) ?? null, fileData: p.fileData ?? null, createdAt: new Date().toISOString() });
    return json({ ok: true, id });
  } catch (e) { return json({ error: errMsg(e) }, 400); }
}

// GET ?bot=…&ids=a,b → status of specific commands; otherwise the 30 most recent for that bot
export async function GET(req: Request) {
  try {
    const u = new URL(req.url), bot = u.searchParams.get('bot') ?? '', ids = (u.searchParams.get('ids') ?? '').split(',').filter(Boolean).slice(0, 50);
    const cols = { id: botCommands.id, action: botCommands.action, payload: botCommands.payload, fileName: botCommands.fileName, status: botCommands.status, result: botCommands.result, createdAt: botCommands.createdAt, doneAt: botCommands.doneAt };
    const db = getDb();
    const rows = ids.length
      ? await db.select(cols).from(botCommands).where(inArray(botCommands.id, ids))
      : await db.select(cols).from(botCommands).where(eq(botCommands.bot, bot)).orderBy(desc(botCommands.createdAt)).limit(30);
    return json({ commands: rows.map(r => ({ ...r, payload: JSON.parse(r.payload || '{}'), result: r.result ? JSON.parse(r.result) : null })) });
  } catch (e) { return json({ error: errMsg(e) }, 500); }
}

// DELETE ?id= → cancel a command that hasn't started yet
export async function DELETE(req: Request) {
  const id = new URL(req.url).searchParams.get('id') ?? '';
  const r = await getDb().delete(botCommands).where(and(eq(botCommands.id, id), eq(botCommands.status, 'pending'))).returning({ id: botCommands.id });
  return r.length ? json({ ok: true }) : json({ error: 'এই কাজ আগেই শুরু হয়ে গেছে।' }, 409);
}
