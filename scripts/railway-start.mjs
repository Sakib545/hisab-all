// Start Nexa Hisab on Railway (or any Linux host / VPS).
//  - database lives in DATA_DIR (mount a Railway Volume at /data)
//  - new drizzle/*.sql migrations are applied once, automatically
//  - listens on 0.0.0.0:$PORT; secrets go to dist/server/.dev.vars, never the command line
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const config = join(root, "dist/server/wrangler.json");
const wrangler = join(root, "node_modules/wrangler/bin/wrangler.js");
const sitesEnv = join(root, "scripts/sites-env.mjs");
if (!existsSync(config)) {
  console.error("dist/server/wrangler.json নেই — আগে `pnpm run build` চালান (Railway-তে Build Command)।");
  process.exit(1);
}
const dataDir = process.env.DATA_DIR || (existsSync("/data") ? "/data/nexa-hisab" : join(root, ".wrangler/state"));
mkdirSync(dataDir, { recursive: true });
if (process.env.RAILWAY_ENVIRONMENT && !existsSync("/data") && !process.env.DATA_DIR) {
  console.warn("⚠️  No Railway Volume at /data — the database will be LOST on every redeploy. Add a Volume mounted at /data.");
}

// ---- migrations ---------------------------------------------------------------
const marker = join(dataDir, "nexa-migrations.json");
const applied = new Set(existsSync(marker) ? JSON.parse(readFileSync(marker, "utf8")) : []);
const files = readdirSync(join(root, "drizzle")).filter(f => /^\d{4}_.*\.sql$/.test(f)).sort();
for (const f of files) {
  if (applied.has(f)) continue;
  console.log(`→ migration ${f}`);
  const r = spawnSync(process.execPath, ["--import", sitesEnv, wrangler, "d1", "execute", "DB", "--local",
    "--config", config, "--persist-to", dataDir, "--file", join(root, "drizzle", f)], { encoding: "utf8" });
  const out = `${r.stdout}\n${r.stderr}`;
  if (r.status !== 0) {
    // database made before this script existed: the migration is already in it
    if (/already exists|duplicate column/i.test(out)) console.log(`  (already applied)`);
    else { console.error(out); process.exit(1); }
  }
  applied.add(f);
  writeFileSync(marker, JSON.stringify([...applied].sort(), null, 2));
}

// ---- secrets → .dev.vars (read by wrangler, not visible in `ps`) ------------------
const vars = { REQUIRE_LOGIN: process.env.RAILWAY_ENVIRONMENT || process.env.REQUIRE_LOGIN === "1" ? "1" : "0" };
for (const k of ["APP_PASSWORD", "BOT_SYNC_TOKEN"]) if (process.env[k]) vars[k] = process.env[k];
writeFileSync(join(root, "dist/server/.dev.vars"),
  Object.entries(vars).map(([k, v]) => `${k}=${JSON.stringify(String(v))}`).join("\n") + "\n", { mode: 0o600 });
if (vars.REQUIRE_LOGIN === "1" && !vars.APP_PASSWORD) console.warn("⚠️  APP_PASSWORD not set — the site will only show a setup notice until you add it.");

// ---- run ------------------------------------------------------------------------
const port = process.env.PORT || "8787";
console.log(`Nexa Hisab → http://0.0.0.0:${port}  (data: ${dataDir})`);
const child = spawn(process.execPath, ["--import", sitesEnv, wrangler, "dev", "--config", config, "--local",
  "--persist-to", dataDir, "--ip", "0.0.0.0", "--port", port, "--inspector-port", "0",
  "--show-interactive-dev-session=false"], { stdio: "inherit", env: { ...process.env, CI: "1" } });
for (const sig of ["SIGTERM", "SIGINT"]) process.on(sig, () => child.kill(sig));
child.on("exit", code => process.exit(code ?? 0));
