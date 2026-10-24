// Simple password login for self-hosting (Railway, a VPS…). Off when APP_PASSWORD is not set,
// except where REQUIRE_LOGIN=1 (set by scripts/railway-start.mjs) — then the app refuses to show data.
// Bots never need it: /api/bot/* is protected by each bot's own key.
const COOKIE = 'nh_auth';
const MAX_AGE = 60 * 60 * 24 * 30;

async function sessionToken(password: string) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`nexa-hisab-session:${password}`));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}
function same(a: string, b: string) {
  const x = new TextEncoder().encode(a), y = new TextEncoder().encode(b);
  let d = x.length ^ y.length;
  for (let i = 0; i < y.length; i++) d |= (x[i] ?? 0) ^ y[i];
  return d === 0;
}
function cookie(req: Request, name: string) {
  return (req.headers.get('cookie') ?? '').split(/;\s*/).find(c => c.startsWith(name + '='))?.slice(name.length + 1) ?? '';
}
const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!));

function page(body: string, status = 200) {
  return new Response(`<!doctype html><html lang="bn"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nexa Hisab · Login</title>
<style>:root{color-scheme:light dark}body{margin:0;min-height:100vh;display:grid;place-items:center;font-family:Inter,"Noto Sans Bengali",system-ui,sans-serif;background:#f7f9f8;color:#29312f}
@media(prefers-color-scheme:dark){body{background:#111614;color:#e6ece8}.card{background:#1a201d!important;border-color:#2a332e!important}input{background:#111614!important;color:#e6ece8!important;border-color:#2a332e!important}}
.card{width:min(360px,calc(100vw - 40px));background:#fff;border:1px solid #e6ebe8;border-radius:16px;padding:30px 28px;box-sizing:border-box}
.logo{display:flex;align-items:center;gap:10px;font-weight:700;font-size:20px;margin-bottom:22px}.logo i{width:34px;height:34px;border-radius:9px;background:#27775d;display:grid;place-items:center;color:#fff;font-style:normal}
label{display:block;font-size:12px;font-weight:600;margin-bottom:6px;color:#5d6761}input{width:100%;box-sizing:border-box;border:1px solid #dfe5e1;border-radius:9px;padding:12px;font-size:15px}
button{margin-top:14px;width:100%;border:0;border-radius:9px;padding:12px;background:#27775d;color:#fff;font-weight:600;font-size:14px;cursor:pointer}
.err{color:#a3392b;font-size:12.5px;margin:10px 0 0}p{font-size:13px;line-height:1.6;color:#7b847e}code{background:#eef1ef;padding:1px 5px;border-radius:4px;color:#29312f}</style></head>
<body><main class="card"><div class="logo"><i>n</i>nexa hisab</div>${body}</main></body></html>`,
    { status, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'x-frame-options': 'DENY' } });
}
const loginForm = (error = '', next = '/') => page(`<form method="post" action="/__login"><input type="hidden" name="next" value="${esc(next)}">
<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" autofocus required>
${error ? `<p class="err" role="alert">${esc(error)}</p>` : ''}<button type="submit">Login</button></form>`, error ? 401 : 200);

/** Returns a Response when the request must not reach the app, otherwise null. */
export async function authGate(req: Request, env: { APP_PASSWORD?: string; REQUIRE_LOGIN?: string }): Promise<Response | null> {
  const url = new URL(req.url);
  if (url.pathname === '/__health') return new Response('ok', { headers: { 'cache-control': 'no-store' } });
  if (url.pathname.startsWith('/api/bot/')) return null;
  const password = env.APP_PASSWORD ?? '';
  if (!password) {
    if (env.REQUIRE_LOGIN !== '1') return null;
    return url.pathname.startsWith('/api/')
      ? Response.json({ error: 'APP_PASSWORD not set' }, { status: 503 })
      : page(`<p>Data সুরক্ষিত রাখতে login চালু করতে হবে।</p><p>Railway → এই service → <b>Variables</b>-এ <code>APP_PASSWORD</code> যোগ করুন (১০+ অক্ষরের password), তারপর redeploy।</p>`, 503);
  }
  const secure = url.protocol === 'https:' || req.headers.get('x-forwarded-proto') === 'https';
  const attrs = `Path=/; HttpOnly; SameSite=Lax${secure ? '; Secure' : ''}`;
  if (url.pathname === '/__logout') {
    return new Response(null, { status: 303, headers: { location: '/', 'set-cookie': `${COOKIE}=; ${attrs}; Max-Age=0` } });
  }
  if (url.pathname === '/__login' && req.method === 'POST') {
    const form = await req.formData().catch(() => null);
    const given = String(form?.get('password') ?? '');
    const next = String(form?.get('next') ?? '/');
    const safeNext = next.startsWith('/') && !next.startsWith('//') ? next : '/';
    if (!same(given, password)) {
      await new Promise(r => setTimeout(r, 800)); // slow down guessing
      return loginForm('Password ঠিক নেই।', safeNext);
    }
    return new Response(null, { status: 303, headers: { location: safeNext, 'set-cookie': `${COOKIE}=${await sessionToken(password)}; ${attrs}; Max-Age=${MAX_AGE}` } });
  }
  if (same(cookie(req, COOKIE), await sessionToken(password))) return null;
  if (url.pathname.startsWith('/api/')) return Response.json({ error: 'login required' }, { status: 401 });
  if (req.method !== 'GET' && req.method !== 'HEAD') return new Response('login required', { status: 401 });
  return loginForm('', url.pathname + url.search);
}
