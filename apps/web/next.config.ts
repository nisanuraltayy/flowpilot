import type { NextConfig } from "next";

/**
 * Temel security response header'ları (FP-OPS-003B) — TÜM route'lara uygulanır.
 *
 * Bilinçli olarak BURADA OLMAYANLAR (ayrı karar/dilim gerektirir; bkz.
 * docs/operations/http-security.md §7):
 * - Content-Security-Policy: App Router inline script'leri nonce tabanlı dinamik
 *   CSP ister; statik config CSP'si build'i kırma riski taşır → ayrı dilim.
 * - Strict-Transport-Security: TLS termination edge'dedir; sağlayıcı kararına bağlı.
 * - CORS header'ları: backend server-only trafik modelinde gereksizdir.
 */
const SECURITY_HEADERS: ReadonlyArray<{ key: string; value: string }> = [
  // MIME sniffing kapalı.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Ürün kapsamında iframe/embed gereksinimi YOK → framing tamamen engelli.
  { key: "X-Frame-Options", value: "DENY" },
  // Cross-origin isteklere tam URL/path sızmaz; same-origin navigasyon korunur.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Kullanılmayan güçlü browser yetenekleri kapalı.
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  // Browsing-context izolasyonu; popup tabanlı OAuth/window.open akışı YOKTUR.
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  // Container packaging (FP-OPS-001): standalone output, uygulamanın çalışması için
  // gereken minimum dosya kümesini `.next/standalone` altına üretir; production
  // image'ında dev/build bağımlılıkları taşınmaz.
  output: "standalone",
  async headers() {
    return [
      {
        // Catch-all: sayfalar, route handler'lar ve static asset'ler dahil.
        source: "/(.*)",
        headers: [...SECURITY_HEADERS],
      },
    ];
  },
};

export default nextConfig;
