import { env } from 'cloudflare:workers';
import { eq, and, inArray, like, sql, lt } from 'drizzle-orm';
import { getDb } from '../db';
import { bots, botRecords, entries, botCommands } from '../db/schema';
import { cleanBotName, cleanRecord, sha256Hex, tokenMatches, MAX_BATCH, type BotRecordInput, type CleanRecord } from './bot-sync';

export const json = (d: unknown, status = 200) => Response.json(d, { status });
export const errMsg = (e: unknown) => {
  const full = String(e) + ' ' + String((e as { cause?: unknown })?.cause ?? '');
  if (full.includes('UNIQUE')) return 'UNIQUE constraint';
  return String(e).replace(/^Error: /, '').replace(/^Failed query:[\s\S]*/, 'Database error').slice(0, 300);
};
// D1 allows max 100 bound parameters per statement → keep IN() lists below that.
export const chunk = <T,>(a: T[], n = 90) => Array.from({ length: Math.ceil(a.length / n) }, (_, i) => a.slice(i * n, i * n + n));

/** Which bot is calling: per-bot key from the Bot hub, or master BOT_SYNC_TOKEN + bot name. */
export async function resolveBot(req: Request, nameHint?: unknown): Promise<string | null> {
  const h = req.headers.get('authorization') ?? '';
  const token = h.startsWith('Bearer ') ? h.slice(7).trim() : '';
  if (!token) return null;
  const db = getDb();
  if (token.startsWith('nxh_')) {
    const row = await db.select({ name: bots.name }).from(bots).where(eq(bots.tokenHash, await sha256Hex(token))).get();
    return row?.name ?? null;
  }
  if (!tokenMatches(token, env.BOT_SYNC_TOKEN)) return null;
  const name = cleanBotName(nameHint);
  await db.insert(bots).values({ id: crypto.randomUUID(), name, label: name, kind: 'general', createdAt: new Date().toISOString() }).onConflictDoNothing({ target: bots.name });
  return name;
}

export type IngestResult = { id: string; status: 'created' | 'updated' | 'duplicate' | 'error'; error?: string; ledger?: boolean };

/**
 * Few queries per call: 1 lookup per 90 ids + 1–3 writes per new/changed record, sent as one batch.
 * upsert: a record that already exists but whose content changed (hash differs) is updated,
 * including its ledger entry. Without upsert, existing records are left untouched.
 */
export async function ingest(bot: string, list: BotRecordInput[], upsert = false) {
  if (!Array.isArray(list) || !list.length || list.length > MAX_BATCH) throw Error(`records: 1-${MAX_BATCH} items`);
  const db = getDb(), now = new Date(), nowIso = now.toISOString();
  const results: IngestResult[] = [];
  const valid: CleanRecord[] = [];
  const seen = new Set<string>();
  for (const raw of list) {
    const id = String(raw?.id ?? '');
    try {
      const r = cleanRecord(bot, raw, now);
      if (seen.has(r.externalId)) { results.push({ id, status: 'duplicate' }); continue; }
      seen.add(r.externalId); valid.push(r);
      results.push({ id: r.externalId, status: 'created', ledger: !!r.entry });
    } catch (e) { results.push({ id, status: 'error', error: errMsg(e) }); }
  }
  const existing = new Map<string, { id: string; hash: string; entryId: string | null }>();
  for (const ids of chunk(valid.map(v => v.externalId))) {
    const rows = await db.select({ x: botRecords.externalId, id: botRecords.id, hash: botRecords.contentHash, entryId: botRecords.entryId })
      .from(botRecords).where(and(eq(botRecords.bot, bot), inArray(botRecords.externalId, ids)));
    rows.forEach(r => existing.set(r.x, { id: r.id, hash: r.hash, entryId: r.entryId }));
  }
  const stmts: any[] = [];
  for (const r of valid) {
    const res = results.find(x => x.id === r.externalId && x.status === 'created')!;
    const ex = existing.get(r.externalId);
    if (ex) {
      if (!upsert || ex.hash === r.hash) { res.status = 'duplicate'; delete res.ledger; continue; }
      res.status = 'updated';
      stmts.push(db.update(botRecords).set({ kind: r.kind, title: r.title, amount: r.amount, status: r.status, data: r.data, occurredAt: r.occurredAt, contentHash: r.hash }).where(eq(botRecords.id, ex.id)));
      if (r.entry) {
        const { reference, ...fields } = r.entry;
        stmts.push(db.insert(entries).values({ id: crypto.randomUUID(), ...r.entry, createdAt: nowIso }).onConflictDoUpdate({ target: entries.reference, set: fields }));
        if (!ex.entryId) stmts.push(db.update(botRecords).set({ entryId: sql`(select ${entries.id} from ${entries} where ${entries.reference} = ${reference})` }).where(eq(botRecords.id, ex.id)));
      } else if (ex.entryId) {
        // record no longer belongs in the ledger
        stmts.push(db.delete(entries).where(and(eq(entries.id, ex.entryId), like(entries.reference, `tg:${bot}:%`))));
        stmts.push(db.update(botRecords).set({ entryId: null }).where(eq(botRecords.id, ex.id)));
      }
      continue;
    }
    if (r.entry) stmts.push(db.insert(entries).values({ id: crypto.randomUUID(), ...r.entry, createdAt: nowIso }).onConflictDoNothing({ target: entries.reference }));
    stmts.push(db.insert(botRecords).values({
      id: crypto.randomUUID(), bot, externalId: r.externalId, kind: r.kind, title: r.title, amount: r.amount, status: r.status,
      data: r.data, occurredAt: r.occurredAt, receivedAt: nowIso, contentHash: r.hash,
      entryId: r.entry ? sql`(select ${entries.id} from ${entries} where ${entries.reference} = ${r.entry.reference})` : null,
    }).onConflictDoNothing());
  }
  const failed = results.filter(r => r.status === 'error');
  stmts.push(db.update(bots).set({ lastSeenAt: nowIso, lastError: failed.length ? `${failed.length} rejected · ${failed[0].error}` : null }).where(eq(bots.name, bot)));
  await db.batch(stmts as [any, ...any[]]);
  const count = (s: string) => results.filter(r => r.status === s).length;
  return { ok: true, bot, created: count('created'), updated: count('updated'), duplicate: count('duplicate'), failed: failed.length, results };
}

/** Snapshot reconcile: remove records of one kind that the bot no longer has (and the ledger entries it made for them). */
export async function reconcile(bot: string, kind: string, ids: string[]) {
  const db = getDb();
  const keep = new Set(ids.map(String));
  const rows = await db.select({ id: botRecords.id, x: botRecords.externalId, entryId: botRecords.entryId }).from(botRecords).where(and(eq(botRecords.bot, bot), eq(botRecords.kind, kind)));
  const gone = rows.filter(r => !keep.has(r.x));
  const stmts: any[] = [];
  for (const c of chunk(gone.map(g => g.id))) stmts.push(db.delete(botRecords).where(inArray(botRecords.id, c)));
  for (const c of chunk(gone.map(g => g.entryId).filter(Boolean) as string[])) stmts.push(db.delete(entries).where(and(inArray(entries.id, c), like(entries.reference, `tg:${bot}:%`))));
  stmts.push(db.update(bots).set({ lastSeenAt: new Date().toISOString() }).where(eq(bots.name, bot)));
  await db.batch(stmts as [any, ...any[]]);
  return { ok: true, bot, kind, kept: rows.length - gone.length, removed: gone.length };
}

export async function touch(bot: string) {
  await getDb().update(bots).set({ lastSeenAt: new Date().toISOString() }).where(eq(bots.name, bot));
}

// ---- command queue (site → bot) ------------------------------------------------
export const COMMAND_STALE_MS = 10 * 60 * 1000;

export async function claimCommands(bot: string, max = 3) {
  const db = getDb(), now = new Date();
  // a bot that crashed mid-command: give the command back after 10 minutes
  await db.update(botCommands).set({ status: 'pending', pickedAt: null })
    .where(and(eq(botCommands.bot, bot), eq(botCommands.status, 'running'), lt(botCommands.pickedAt, new Date(now.getTime() - COMMAND_STALE_MS).toISOString())));
  const rows = await db.select().from(botCommands).where(and(eq(botCommands.bot, bot), eq(botCommands.status, 'pending'))).orderBy(botCommands.createdAt).limit(max);
  if (rows.length) await db.update(botCommands).set({ status: 'running', pickedAt: now.toISOString() }).where(inArray(botCommands.id, rows.map(r => r.id)));
  await touch(bot);
  return rows.map(r => ({ id: r.id, action: r.action, payload: JSON.parse(r.payload || '{}'), file_name: r.fileName, file_data: r.fileData, created_at: r.createdAt }));
}

export async function finishCommand(bot: string, id: string, ok: boolean, result: unknown) {
  const res = await getDb().update(botCommands)
    .set({ status: ok ? 'done' : 'failed', result: JSON.stringify(result ?? {}).slice(0, 20000), doneAt: new Date().toISOString(), fileData: null })
    .where(and(eq(botCommands.id, id), eq(botCommands.bot, bot))).returning({ id: botCommands.id });
  return res.length > 0;
}
