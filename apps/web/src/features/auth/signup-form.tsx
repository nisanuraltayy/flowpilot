"use client";

/**
 * Kayıt formu — server action ile çalışır. Password hiçbir state/debug
 * çıktısına yazılmaz; form verisi doğrudan action'a gider.
 */

import Link from "next/link";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { FormField } from "@/components/form-field";
import { SubmitButton } from "@/components/submit-button";
import { IDLE_RESULT, type ActionResult } from "@/features/auth/action-result";
import { MIN_PASSWORD_LENGTH } from "@/features/auth/schemas";

interface SignupFormProps {
  readonly action: (previous: ActionResult, formData: FormData) => Promise<ActionResult>;
}

export function SignupForm({ action }: SignupFormProps) {
  const [result, formAction] = useActionState(action, IDLE_RESULT);

  return (
    <form action={formAction} className="flex flex-col gap-4" noValidate>
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
        autoComplete="new-password"
        required
        hint={`En az ${MIN_PASSWORD_LENGTH} karakter.`}
        errors={result.status === "error" ? result.fieldErrors?.password : undefined}
      />
      <FormField
        label="Şifre (tekrar)"
        name="passwordConfirm"
        type="password"
        autoComplete="new-password"
        required
        errors={result.status === "error" ? result.fieldErrors?.passwordConfirm : undefined}
      />

      <SubmitButton pendingLabel="Kayıt oluşturuluyor…">Kayıt ol</SubmitButton>

      <p className="text-center text-sm text-slate-600">
        Zaten hesabın var mı?{" "}
        <Link
          href="/login"
          className="font-medium text-blue-600 hover:text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          Giriş yap
        </Link>
      </p>
    </form>
  );
}
