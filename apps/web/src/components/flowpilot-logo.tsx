/**
 * FlowPilot marka işareti — sade inline SVG (harici görsel/font YOK).
 *
 * İşaret: birbirine bağlanan üç adım + ileri yön (akış/onay ilerlemesi) —
 * FlowPilot'ın "talebi kurala göre yönlendir, onayı deterministik yürüt" değerini
 * soyut ve sade biçimde anlatır. Aşırı illüstrasyon/animasyon yoktur.
 */

interface FlowPilotLogoProps {
  /** Sadece işaret (wordmark olmadan) — dar/mobil alanlar için. */
  readonly markOnly?: boolean;
  /** Koyu zemin üzerinde (ör. sidebar) beyaz wordmark. */
  readonly onDark?: boolean;
}

export function FlowPilotMark({ className = "h-8 w-8" }: { readonly className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      role="img"
      aria-label="FlowPilot"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="32" height="32" rx="8" className="fill-brand-600" />
      {/* Birbirine bağlanan adımlar + ileri akış */}
      <circle cx="9" cy="11" r="2.4" className="fill-white" />
      <circle cx="9" cy="21" r="2.4" fill="#a5b4fc" />
      <circle cx="23" cy="16" r="2.4" className="fill-white" />
      <path
        d="M11 11.6 L21 15.2 M11 20.4 L21 16.8"
        stroke="#c7d2fe"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      {/* İleri yön oku */}
      <path
        d="M20.5 13.4 L24 16 L20.5 18.6"
        stroke="white"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

export function FlowPilotLogo({ markOnly = false, onDark = false }: FlowPilotLogoProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 text-lg font-bold tracking-tight ${
        onDark ? "text-white" : "text-slate-900"
      }`}
    >
      <FlowPilotMark />
      {markOnly ? null : "FlowPilot"}
    </span>
  );
}
