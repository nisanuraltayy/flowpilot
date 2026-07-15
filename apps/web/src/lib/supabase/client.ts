/**
 * Browser Supabase istemcisi — YALNIZ client component'lerde kullanılır.
 *
 * Supabase yalnız AUTHENTICATION sağlayıcısıdır (ADR-005): browser'dan hiçbir
 * Supabase business/database tablosuna erişilmez. FlowPilot verisi yalnız
 * FastAPI üzerinden yönetilir.
 */

import { createBrowserClient } from "@supabase/ssr";

import { getSupabaseConfig } from "@/lib/env";

export function createClient() {
  const config = getSupabaseConfig();
  if (config === null) {
    return null;
  }
  return createBrowserClient(config.url, config.publishableKey);
}
