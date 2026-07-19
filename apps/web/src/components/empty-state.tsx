/** Boş durum ekranı — sahte veri yerine dürüst "henüz yok" mesajı + isteğe bağlı aksiyon. */

interface EmptyStateProps {
  readonly title: string;
  readonly description: string;
  readonly icon?: string;
  readonly action?: React.ReactNode;
}

export function EmptyState({ title, description, icon = "📋", action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
      <span
        aria-hidden="true"
        className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-2xl"
      >
        {icon}
      </span>
      <h2 className="text-base font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
