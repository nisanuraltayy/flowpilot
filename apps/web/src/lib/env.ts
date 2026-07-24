/**
 * Merkezi, typed environment yapılandırması.
 *
 * Kurallar:
 * - FLOWPILOT_API_BASE_URL SERVER-ONLY'dir; browser bundle'a girmez
 *   (NEXT_PUBLIC_ öneki yok).
 * - Service role key ve JWT secret BURADA YOKTUR ve ASLA eklenmez.
 * - Secret/token loglanmaz; hata mesajlarında YALNIZ değişken ADI geçer, DEĞER geçmez.
 *
 * Production fail-fast (FP-OPS-001):
 * - Production runtime'da eksik değişken SESSİZCE localhost'a düşmez — anlaşılır hata verir.
 *   Böylece yanlış yapılandırılmış bir deployment, kullanıcıya bozuk davranış göstermek
 *   yerine açıkça başarısız olur.
 * - Build (prerender) sırasında bu kontrol UYGULANMAZ: `next build` deployment
 *   secret'larına sahip olmadan çalışabilmelidir (CI'da olduğu gibi). Kontrol yalnız
 *   gerçek istek anında (runtime) devreye girer.
 */

const DEV_API_BASE_URL = "http://127.0.0.1:8000";
const DEV_APP_URL = "http://localhost:3000";

export interface SupabaseConfig {
  readonly url: string;
  readonly publishableKey: string;
}

/** Next.js production BUILD fazı mı? (prerender sırasında runtime secret'ı beklenmez.) */
function isBuildPhase(): boolean {
  return process.env.NEXT_PHASE === "phase-production-build";
}

/** Gerçek production RUNTIME mı? (build fazı hariç.) */
function isProductionRuntime(): boolean {
  return process.env.NODE_ENV === "production" && !isBuildPhase();
}

/**
 * Production runtime'da zorunlu değişkeni döndürür; eksikse ANLAŞILIR hata verir.
 * Development/test'te güvenli local default'a düşer. Hata mesajı DEĞER içermez.
 */
function requireInProduction(name: string, value: string | undefined, devDefault: string): string {
  if (value !== undefined && value !== "") {
    return value;
  }
  if (isProductionRuntime()) {
    throw new Error(
      `${name} tanımlı değil. Production'da bu değişken zorunludur; ` +
        "local adrese sessizce düşülmez.",
    );
  }
  return devDefault;
}

/**
 * Supabase public yapılandırması.
 *
 * Development/test: eksikse `null` → çağıran taraf kontrollü "yapılandırılmamış" mesajı gösterir.
 * Production runtime: eksikse ANLAŞILIR hata (fail-fast) — sessiz bozuk auth akışı olmaz.
 */
export function getSupabaseConfig(): SupabaseConfig | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !publishableKey) {
    if (isProductionRuntime()) {
      const missing = [
        url ? null : "NEXT_PUBLIC_SUPABASE_URL",
        publishableKey ? null : "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
      ].filter((n): n is string => n !== null);
      throw new Error(
        `Supabase yapılandırması eksik: ${missing.join(", ")}. ` +
          "Production'da bu değişkenler zorunludur. NEXT_PUBLIC_* değerleri BUILD " +
          "sırasında gömülür; düzeltmek için build argümanlarıyla yeniden derleyin.",
      );
    }
    return null;
  }
  return { url, publishableKey };
}

/** FlowPilot FastAPI taban adresi — YALNIZ server tarafında kullanılır. */
export function getApiBaseUrl(): string {
  return requireInProduction(
    "FLOWPILOT_API_BASE_URL",
    process.env.FLOWPILOT_API_BASE_URL,
    DEV_API_BASE_URL,
  );
}

/** Uygulamanın kendi public adresi (auth callback + davet linki için). */
export function getAppUrl(): string {
  return requireInProduction("NEXT_PUBLIC_APP_URL", process.env.NEXT_PUBLIC_APP_URL, DEV_APP_URL);
}
