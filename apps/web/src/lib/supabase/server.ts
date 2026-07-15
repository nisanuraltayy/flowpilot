/**
 * Server Supabase istemcisi — Server Component, Server Action ve Route
 * Handler'larda kullanılır.
 *
 * Cookie adapter'ı güncel TOPLU API'yi kullanır (getAll/setAll); deprecated
 * tekil get/set/remove YOKTUR. Service role KULLANILMAZ — yalnız publishable
 * key ile authentication.
 */

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { getSupabaseConfig } from "@/lib/env";

export async function createClient() {
  const config = getSupabaseConfig();
  if (config === null) {
    return null;
  }

  const cookieStore = await cookies();

  return createServerClient(config.url, config.publishableKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Server Component içinden set çağrısı yok sayılır; session
          // yenilemesi proxy katmanında yapılır.
        }
      },
    },
  });
}
