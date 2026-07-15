"use client";

/**
 * Pending-farkındalıklı submit butonu. Form action beklerken disabled olur —
 * çift submit'i engeller; durum yalnız renkle değil metinle de anlatılır.
 */

import { useFormStatus } from "react-dom";

interface SubmitButtonProps {
  readonly children: string;
  readonly pendingLabel: string;
}

export function SubmitButton({ children, pendingLabel }: SubmitButtonProps) {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      className="inline-flex w-full items-center justify-center rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-blue-300"
    >
      {pending ? pendingLabel : children}
    </button>
  );
}
