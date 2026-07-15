/**
 * Erişilebilir geri bildirim mesajı. `aria-live` ile ekran okuyucuya duyurulur;
 * durum ikon + metinle anlatılır (yalnız renk değil).
 */

interface AlertProps {
  readonly tone: "error" | "success" | "info";
  readonly children: React.ReactNode;
}

const TONE_STYLES: Record<AlertProps["tone"], { box: string; icon: string }> = {
  error: { box: "border-red-200 bg-red-50 text-red-800", icon: "⚠" },
  success: { box: "border-green-200 bg-green-50 text-green-800", icon: "✓" },
  info: { box: "border-blue-200 bg-blue-50 text-blue-800", icon: "ℹ" },
};

export function Alert({ tone, children }: AlertProps) {
  const style = TONE_STYLES[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      aria-live={tone === "error" ? "assertive" : "polite"}
      className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm ${style.box}`}
    >
      <span aria-hidden="true" className="mt-0.5 shrink-0 font-bold">
        {style.icon}
      </span>
      <div>{children}</div>
    </div>
  );
}
