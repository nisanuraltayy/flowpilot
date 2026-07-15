/**
 * Merkezi, typed environment yapılandırması.
 *
 * Kurallar:
 * - Eksik Supabase yapılandırması BUILD'İ PATLATMAZ; auth işlemi çağrıldığında
 *   kontrollü "yapılandırılmamış" sonucu üretilir.
 * - FLOWPILOT_API_BASE_URL SERVER-ONLY'dir; browser bundle'a girmez
 *   (NEXT_PUBLIC_ öneki yok).
 * - Service role key ve JWT secret BURADA YOKTUR ve ASLA eklenmez.
 * - Secret/token loglanmaz.
 */

export interface SupabaseConfig {
  readonly url: string;
  readonly publishableKey: string;
}

/** Supabase public yapılandırması; eksikse null (kontrollü degrade). */
export function getSupabaseConfig(): SupabaseConfig | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !publishableKey) {
    return null;
  }
  return { url, publishableKey };
}

/** FlowPilot FastAPI taban adresi — YALNIZ server tarafında kullanılır. */
export function getApiBaseUrl(): string {
  return process.env.FLOWPILOT_API_BASE_URL ?? "http://127.0.0.1:8000";
}

/** Uygulamanın kendi public adresi (auth callback URL'i için). */
export function getAppUrl(): string {
  return process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
}
