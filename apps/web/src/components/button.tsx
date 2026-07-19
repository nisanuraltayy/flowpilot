/**
 * Merkezi buton stilleri — primary/secondary/danger. Hem `<Link>` (ButtonLink) hem
 * `<button>` (SubmitButton, karar butonları) aynı sınıf setini kullanır; her yerde
 * hex/utility tekrarı yok.
 */

import Link from "next/link";

export type ButtonVariant = "primary" | "secondary" | "danger" | "success";
export type ButtonSize = "sm" | "md";

const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-lg font-semibold transition-colors " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 " +
  "disabled:cursor-not-allowed disabled:opacity-60";

const SIZE: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2.5 text-sm",
};

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-brand-600 text-white shadow-sm hover:bg-brand-700 focus-visible:ring-brand-500 disabled:bg-brand-300 disabled:opacity-100",
  secondary:
    "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 focus-visible:ring-brand-500",
  danger:
    "border border-red-300 bg-white text-red-700 hover:bg-red-50 focus-visible:ring-red-500",
  success:
    "bg-green-600 text-white shadow-sm hover:bg-green-700 focus-visible:ring-green-500 disabled:bg-green-300 disabled:opacity-100",
};

export function buttonClasses(variant: ButtonVariant = "primary", size: ButtonSize = "md"): string {
  return `${BASE} ${SIZE[size]} ${VARIANT[variant]}`;
}

interface ButtonLinkProps {
  readonly href: string;
  readonly children: React.ReactNode;
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  readonly className?: string;
}

export function ButtonLink({
  href,
  children,
  variant = "primary",
  size = "md",
  className = "",
}: ButtonLinkProps) {
  return (
    <Link href={href} className={`${buttonClasses(variant, size)} ${className}`}>
      {children}
    </Link>
  );
}
