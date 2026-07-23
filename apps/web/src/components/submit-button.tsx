"use client";

/**
 * Pending-farkındalıklı submit butonu. Form action beklerken disabled olur —
 * çift submit'i engeller; durum yalnız renkle değil metinle de anlatılır.
 */

import { useFormStatus } from "react-dom";

import { buttonClasses, type ButtonVariant } from "@/components/button";

interface SubmitButtonProps {
  readonly children: string;
  readonly pendingLabel: string;
  readonly variant?: ButtonVariant;
  readonly fullWidth?: boolean;
  /**
   * Submit dispatch'inden ÖNCE (native click sırasında) senkron çalışır — ör. form
   * serialize edilmeden önce gizli bir alanı doldurmak için (idempotency key). preventDefault
   * ETMEZ; submit akışını değiştirmez.
   */
  readonly onClick?: () => void;
}

export function SubmitButton({
  children,
  pendingLabel,
  variant = "primary",
  fullWidth = true,
  onClick,
}: SubmitButtonProps) {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      aria-busy={pending}
      onClick={onClick}
      className={`${buttonClasses(variant, "md")} ${fullWidth ? "w-full" : ""}`}
    >
      {pending ? pendingLabel : children}
    </button>
  );
}
