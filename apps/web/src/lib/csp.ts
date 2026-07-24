/**
 * Nonce tabanlı Content Security Policy üretimi (FP-OPS-004A).
 *
 * Saf ve deterministik: aynı girdi → aynı politika. Nonce ayrıca üretilir ve
 * HER REQUEST'te yenidir; asla loglanmaz, cookie'ye veya public header'a
 * yazılmaz (yalnız CSP header'ının içinde yaşar).
 *
 * Kurallar (audit + owner kararları):
 * - Production'da `unsafe-eval` / `unsafe-inline` YOK (script ve style).
 * - `data:` / `blob:` / `wss:` / Supabase origin'i / deployment hostname YOK —
 *   browser dış origin'e bağlanmaz (auth dahil her şey server-side).
 * - Development farkı YALNIZ HMR gereksinimleridir: script-src `unsafe-eval`,
 *   style-src `unsafe-inline`, connect-src `ws:`.
 * - Politika tek satırdır ve header-safe'tir; nonce charset'i doğrulanarak
 *   header injection yapısal olarak engellenir.
 */

const NONCE_BYTE_LENGTH = 16; // 128 bit

// Standart base64 alfabesi (btoa çıktısı). CR/LF veya ';' gibi header/politika
// ayracı karakterler bu kümede YOKTUR — injection yapısal olarak imkânsız.
const BASE64_PATTERN = /^[A-Za-z0-9+/]+={0,2}$/;

/** Her çağrıda yeni, 128-bit, base64 kodlu kriptografik nonce üretir. */
export function generateNonce(): string {
  // Web Crypto: hem Node hem edge/proxy runtime'ında mevcut. Node-only
  // `crypto` modülü BİLİNÇLİ olarak import edilmez.
  const bytes = crypto.getRandomValues(new Uint8Array(NONCE_BYTE_LENGTH));
  return btoa(String.fromCharCode(...bytes));
}

export interface ContentSecurityPolicyInput {
  /** `generateNonce()` çıktısı. Başka kaynaktan nonce KABUL EDİLMEZ. */
  readonly nonce: string;
  /** Yalnız development (HMR) gevşetmeleri için; test dahil diğer her ortam strict'tir. */
  readonly development?: boolean;
}

/**
 * Enforce edilecek CSP politikasını üretir (tek satır, deterministik sıra).
 *
 * Geçersiz (base64 olmayan) nonce girişi hata fırlatır — politika asla bozuk
 * veya injection'a açık biçimde üretilmez.
 */
export function buildContentSecurityPolicy(input: ContentSecurityPolicyInput): string {
  if (!BASE64_PATTERN.test(input.nonce)) {
    // Nonce değeri hataya YAZILMAZ (log sızıntısı olmaz); yalnız kural anlatılır.
    throw new Error("CSP nonce base64 karakter setinde olmalıdır");
  }
  const development = input.development === true;

  const scriptSrc = ["'self'", `'nonce-${input.nonce}'`, "'strict-dynamic'"];
  if (development) {
    scriptSrc.push("'unsafe-eval'"); // yalnız dev bundler; production'a SIZAMAZ (testle pinli)
  }
  const styleSrc = development ? ["'self'", "'unsafe-inline'"] : ["'self'"];
  const connectSrc = development ? ["'self'", "ws:"] : ["'self'"];

  const directives: ReadonlyArray<readonly [string, readonly string[]]> = [
    ["default-src", ["'none'"]],
    ["base-uri", ["'self'"]],
    ["object-src", ["'none'"]],
    ["frame-ancestors", ["'none'"]], // X-Frame-Options: DENY ile birebir uyumlu
    ["form-action", ["'self'"]],
    ["script-src", scriptSrc],
    ["style-src", styleSrc],
    ["img-src", ["'self'"]],
    ["font-src", ["'self'"]],
    ["connect-src", connectSrc],
    ["worker-src", ["'none'"]],
    ["frame-src", ["'none'"]],
  ];

  return directives.map(([name, values]) => `${name} ${values.join(" ")}`).join("; ");
}
