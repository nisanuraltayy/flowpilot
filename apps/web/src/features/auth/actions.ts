"use server";

/**
 * Auth server action'ları.
 *
 * Kurallar:
 * - Password ve auth response ASLA loglanmaz.
 * - Kullanıcının var olup olmadığını AÇIĞA ÇIKARAN mesaj üretilmez:
 *   login hatası tek generic mesajdır; signup her durumda aynı akışı izler.
 * - Başarılı akışlar redirect() ile sonlanır.
 */

import { redirect } from "next/navigation";

import {
  errorResult,
  SUPABASE_NOT_CONFIGURED_MESSAGE,
  type ActionResult,
} from "@/features/auth/action-result";
import { signInSchema, signUpSchema } from "@/features/auth/schemas";
import { getAppUrl } from "@/lib/env";
import { sanitizeInternalPath } from "@/lib/redirect";
import { createClient } from "@/lib/supabase/server";

const GENERIC_SIGNIN_ERROR = "E-posta veya şifre hatalı.";
const GENERIC_SIGNUP_ERROR = "Kayıt işlemi şu anda tamamlanamadı. Lütfen tekrar deneyin.";

function fieldErrorsFromZod(error: {
  issues: readonly { path: readonly PropertyKey[]; message: string }[];
}): Record<string, string[]> {
  const fields: Record<string, string[]> = {};
  for (const issue of error.issues) {
    const key = String(issue.path[0] ?? "form");
    fields[key] = [...(fields[key] ?? []), issue.message];
  }
  return fields;
}

export async function signInAction(
  _previous: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = signInSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!parsed.success) {
    return errorResult("Lütfen alanları kontrol edin.", fieldErrorsFromZod(parsed.error));
  }

  const supabase = await createClient();
  if (supabase === null) {
    return errorResult(SUPABASE_NOT_CONFIGURED_MESSAGE);
  }

  const { error } = await supabase.auth.signInWithPassword({
    email: parsed.data.email,
    password: parsed.data.password,
  });
  if (error) {
    // Tek generic mesaj: kullanıcı var/yok bilgisi SIZDIRILMAZ.
    return errorResult(GENERIC_SIGNIN_ERROR);
  }

  // Dönüş yolu YALNIZ uygulama içi relative path olabilir (open-redirect koruması);
  // davet kabul akışı için `next` korunur, aksi hâlde dashboard'a gidilir.
  const next = formData.get("next");
  redirect(sanitizeInternalPath(typeof next === "string" ? next : null, "/dashboard"));
}

export async function signUpAction(
  _previous: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = signUpSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    passwordConfirm: formData.get("passwordConfirm"),
  });
  if (!parsed.success) {
    return errorResult("Lütfen alanları kontrol edin.", fieldErrorsFromZod(parsed.error));
  }

  const supabase = await createClient();
  if (supabase === null) {
    return errorResult(SUPABASE_NOT_CONFIGURED_MESSAGE);
  }

  const { data, error } = await supabase.auth.signUp({
    email: parsed.data.email,
    password: parsed.data.password,
    options: {
      emailRedirectTo: `${getAppUrl()}/auth/callback`,
    },
  });
  if (error) {
    // Var olan kullanıcıyı sızdırmayan generic mesaj.
    return errorResult(GENERIC_SIGNUP_ERROR);
  }

  if (data.session) {
    // E-posta doğrulaması kapalıysa oturum hemen açılır.
    redirect("/onboarding/organization");
  }

  // E-posta doğrulaması gerekli — kullanıcı var/yok ayrımı YAPILMAZ.
  redirect("/auth/check-email");
}

export async function signOutAction(): Promise<void> {
  const supabase = await createClient();
  if (supabase !== null) {
    await supabase.auth.signOut();
  }
  redirect("/login");
}
