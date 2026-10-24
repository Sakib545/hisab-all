// Runs before the build: lists any app file missing from the repo (common after uploading
// through the GitHub website, which takes max 100 files at a time and skips hidden files).
import { existsSync, readFileSync } from "node:fs";
const root = new URL("..", import.meta.url);
const need = JSON.parse(readFileSync(new URL("./required-files.json", import.meta.url), "utf8"));
const missing = need.filter(p => !existsSync(new URL(p, root)));
if (missing.length) {
  const byDir = {};
  for (const p of missing) (byDir[p.includes("/") ? p.split("/").slice(0, -1).join("/") : "(root)"] ??= []).push(p);
  console.error(`\n❌ ${missing.length}টি file repo-তে নেই — এগুলো GitHub-এ upload করুন, তারপর redeploy:\n`);
  for (const [dir, list] of Object.entries(byDir)) console.error(`  ${dir}/  (${list.length})\n    ` + list.slice(0, 12).join("\n    ") + (list.length > 12 ? `\n    …আরও ${list.length - 12}টি` : ""));
  console.error("\nসহজ উপায়: hisab-all.zip থেকে উপরের folder গুলো পুরোটা upload করুন (folder ধরে drag করলে ভেতরের path ঠিক থাকে).\n");
  process.exit(1);
}
console.log(`✓ সব ${need.length}টি app file আছে`);
