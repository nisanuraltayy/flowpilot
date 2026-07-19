/**
 * Erişilebilir form alanı: label + input + hata alanı.
 * Hata, `aria-describedby` ile input'a bağlanır; yalnız renkle anlatılmaz.
 */

import type { InputHTMLAttributes } from "react";

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  readonly label: string;
  readonly name: string;
  readonly hint?: string;
  readonly errors?: readonly string[];
}

export function FormField({ label, name, hint, errors, ...inputProps }: FormFieldProps) {
  const hasError = errors !== undefined && errors.length > 0;
  const errorId = `${name}-error`;
  const hintId = `${name}-hint`;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={name} className="text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={name}
        name={name}
        aria-invalid={hasError || undefined}
        aria-describedby={
          [hasError ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ") ||
          undefined
        }
        className={`rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-colors placeholder:text-slate-400 focus:ring-2 ${
          hasError
            ? "border-red-400 focus:border-red-500 focus:ring-red-100"
            : "border-slate-300 focus:border-brand-500 focus:ring-brand-100"
        }`}
        {...inputProps}
      />
      {hint ? (
        <p id={hintId} className="text-xs text-slate-500">
          {hint}
        </p>
      ) : null}
      {hasError ? (
        <p id={errorId} role="alert" className="text-xs font-medium text-red-600">
          {errors.join(" ")}
        </p>
      ) : null}
    </div>
  );
}
