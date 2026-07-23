"use client";

/**
 * Panoya kopyalama butonu — erişilebilir başarı geri bildirimi (aria-live).
 *
 * Kopyalanan değer (davet bağlantısı) YALNIZ prop olarak alınır; loglanmaz, storage'a
 * yazılmaz. Clipboard API yoksa kullanıcıya elle kopyalama önerilir.
 */

import { useState } from "react";

import { buttonClasses } from "@/components/button";

interface CopyButtonProps {
  readonly value: string;
  readonly label?: string;
  readonly copiedLabel?: string;
}

export function CopyButton({
  value,
  label = "Bağlantıyı kopyala",
  copiedLabel = "Kopyalandı",
}: CopyButtonProps) {
  const [state, setState] = useState<"idle" | "copied" | "error">("idle");

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setState("copied");
    } catch {
      setState("error");
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={handleCopy}
        className={`${buttonClasses("secondary", "sm")} shrink-0`}
      >
        {state === "copied" ? copiedLabel : label}
      </button>
      <span role="status" aria-live="polite" className="text-xs text-slate-500">
        {state === "copied"
          ? "Bağlantı panoya kopyalandı."
          : state === "error"
            ? "Kopyalanamadı. Bağlantıyı elle seçip kopyalayın."
            : ""}
      </span>
    </div>
  );
}
