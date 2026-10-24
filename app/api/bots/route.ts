// Bot hub management (used by the app UI). Protect the whole UI before exposing it publicly.
import { eq, sql, desc } from 'drizzle-orm';
import { getDb } from '../../../db';
import { bots, botRecords } from '../../../db/schema';
import { cleanBotName, slugify, newToken, sha256Hex, BOT_KINDS } from '../../../lib/bot-sync';
import { json, errMsg } from '../../../lib/bot-server';

export async function GET() {
  try {
    const db = getDb();
    const weekAgo = new Date(Date.now() - 7 * 864e5).toISOString();
    const list = await db.select({ id: bots.id, name: bots.name, label: bots.label, kind: bots.kind, tokenHint: bots.tokenHint, createdAt: bots.createdAt, lastSeenAt: bots.lastSeenAt, lastError: bots.lastError }).from(bots).orderBy(desc(bots.lastSeenAt));
    const stats = await db.select({
      bot: botRecords.bot, records: sql<number>`count(*)`, amount: sql<number>`coalesce(sum(${botRecords.amount}),0)`,
      ledger: sql<number>`sum(case when ${botRecords.entryId} is not null then 1 else 0 end)`,
      ledgerAmount: sql<number>`coalesce(sum(case when ${botRecords.entryId} is not null then ${botRecords.amount} else 0 end),0)`,
      week: sql<number>`sum(case when ${botRecords.occurredAt} >= ${weekAgo} then 1 else 0 end)`,
      latest: sql<string>`max(${botRecords.occurredAt})`,
    }).from(botRecords).groupBy(botRecords.bot);
    const daily = await db.select({ bot: botRecords.bot, day: sql<string>`substr(${botRecords.occurredAt},1,10)`, n: sql<number>`count(*)` })
      .from(botRecords).where(sql`${botRecords.occurredAt} >= ${new Date(Date.now() - 14 * 864e5).toISOString()}`).groupBy(botRecords.bot, sql`2`);
    return json({ bots: list.map(b => ({ ...b, stats: stats.find(s => s.bot === b.name) ?? { records: 0, amount: 0, ledger: 0, ledgerAmount: 0, week: 0, latest: null } })), daily });
  } catch (e) { return json({ error: 'Bot তথ্য লোড হয়নি। Database migration (0002_bot_hub.sql) চালানো হয়েছে কিনা দেখুন।', detail: errMsg(e) }, 500); }
}

// POST {label, kind}  → creates bot, returns token ONCE
// POST {id, action:'rotate'} → new token ; {id, action:'rename', label, kind}
export async function POST(req: Request) {
  try {
    const p = await req.json() as { id?: string; action?: string; label?: string; kind?: string; name?: string };
    const db = getDb();
    const kind = (BOT_KINDS as readonly string[]).includes(String(p.kind)) ? String(p.kind) : 'general';
    if (!p.id) {
      const label = String(p.label ?? '').trim().slice(0, 60);
      if (!label) throw Error('Bot-এর নাম দিন।');
      const name = cleanBotName(p.name || slugify(label) || 'bot');
      const token = newToken();
      await db.insert(bots).values({ id: crypto.randomUUID(), name, label, kind, tokenHash: await sha256Hex(token), tokenHint: token.slice(-4), createdAt: new Date().toISOString() });
      return json({ ok: true, name, token });
    }
    if (p.action === 'rotate') {
      const token = newToken();
      const u = await db.update(bots).set({ tokenHash: await sha256Hex(token), tokenHint: token.slice(-4) }).where(eq(bots.id, p.id)).returning({ name: bots.name });
      if (!u.length) throw Error('Bot পাওয়া যায়নি।');
      return json({ ok: true, name: u[0].name, token });
    }
    if (p.action === 'rename') {
      const label = String(p.label ?? '').trim().slice(0, 60);
      if (!label) throw Error('Bot-এর নাম দিন।');
      await db.update(bots).set({ label, kind }).where(eq(bots.id, p.id));
      return json({ ok: true });
    }
    throw Error('Unknown action');
  } catch (e) {
    const m = errMsg(e);
    return json({ error: m.includes('UNIQUE') ? 'এই নামে bot আগে থেকেই আছে। অন্য নাম দিন।' : m }, 400);
  }
}

// DELETE ?id=…&purge=1 → remove bot (purge also deletes its records; ledger entries stay)
export async function DELETE(req: Request) {
  try {
    const u = new URL(req.url), id = u.searchParams.get('id');
    if (!id) throw Error('id missing');
    const db = getDb();
    const b = await db.select().from(bots).where(eq(bots.id, id)).get();
    if (!b) throw Error('Bot পাওয়া যায়নি।');
    if (u.searchParams.get('purge') === '1') await db.delete(botRecords).where(eq(botRecords.bot, b.name));
    await db.delete(bots).where(eq(bots.id, id));
    return json({ ok: true });
  } catch (e) { return json({ error: errMsg(e) }, 400); }
}
