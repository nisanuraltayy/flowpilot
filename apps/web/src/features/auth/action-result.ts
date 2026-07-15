/**
 * Server action sonuç modeli — typed discriminated union.
 *
 * Başarılı akışlar `redirect()` ile sonlanır (geri dönüş yok); action yalnız
 * hata/bilgi durumlarında sonuç döndürür.
 */

export type FieldErrors = Readonly<Record<string, readonly string[]>>;

export type ActionResult =
  | { readonly status: "idle" }
  | {
      readonly status: "error";
      readonly message: string;
      readonly fieldErrors?: FieldErrors;
    };

export const IDLE_RESULT: ActionResult = { status: "idle" };

export function errorResult(message: string, fieldErrors?: FieldErrors): ActionResult {
  return { status: "error", message, fieldErrors };
}

export const SUPABASE_NOT_CONFIGURED_MESSAGE =
  "Kimlik doğrulama henüz yapılandırılmamış. Lütfen sistem yöneticinize başvurun " +
  "(NEXT_PUBLIC_SUPABASE_URL ve NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY gerekli).";
