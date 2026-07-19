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
}

export function SubmitButton({
  children,
  pendingLabel,
  variant = "primary",
  fullWidth = true,
}: SubmitButtonProps) {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      aria-busy={pending}
      className={`${buttonClasses(variant, "md")} ${fullWidth ? "w-full" : ""}`}
    >
      {pending ? pendingLabel : children}
    </button>
  );
}
