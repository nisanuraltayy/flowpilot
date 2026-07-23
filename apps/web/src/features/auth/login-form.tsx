"use client";

/**
 * Login formu — server action ile çalışır.
 *
 * `action` prop olarak alınır: sayfa gerçek server action'ı bağlar; testler
 * fake action enjekte eder. Password hiçbir state/debug çıktısına yazılmaz —
 * form verisi doğrudan action'a gider.
 */

import Link from "next/link";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { FormField } from "@/components/form-field";
import { SubmitButton } from "@/components/submit-button";
import { IDLE_RESULT, type ActionResult } from "@/features/auth/action-result";

interface LoginFormProps {
  readonly action: (previous: ActionResult, formData: FormData) => Promise<ActionResult>;
  /** Başarılı giriş sonrası dönülecek uygulama-içi yol (davet kabul akışı). */
  readonly next?: string;
}

export function LoginForm({ action, next }: LoginFormProps) {
  const [result, formAction] = useActionState(action, IDLE_RESULT);

  return (
    <form action={formAction} className="flex flex-col gap-4" noValidate>
      {next ? <input type="hidden" name="next" value={next} /> : null}
      {result.status === "error" ? <Alert tone="error">{result.message}</Alert> : null}

      <FormField
        label="E-posta"
        name="email"
        type="email"
        autoComplete="email"
        required
        placeholder="ornek@sirket.com"
        errors={result.status === "error" ? result.fieldErrors?.email : undefined}
      />
      <FormField
        label="Şifre"
        name="password"
        type="password"
        autoComplete="current-password"
        required
        errors={result.status === "error" ? result.fieldErrors?.password : undefined}
      />

      <SubmitButton pendingLabel="Giriş yapılıyor…">Giriş yap</SubmitButton>

      <p className="text-center text-sm text-slate-600">
        Hesabın yok mu?{" "}
        <Link
          href="/signup"
          className="font-medium text-brand-600 hover:text-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          Kayıt ol
        </Link>
      </p>
    </form>
  );
}
