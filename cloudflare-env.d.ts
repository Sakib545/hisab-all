declare namespace Cloudflare {
  interface Env {
    DB?: D1Database;
    BUCKET?: R2Bucket;
    BOT_SYNC_TOKEN?: string;
    APP_PASSWORD?: string;
    REQUIRE_LOGIN?: string;
  }
}
