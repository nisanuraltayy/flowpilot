/** Basit yükleniyor iskeleti (pulse). Route `loading.tsx`'lerinde kullanılır. */

interface SkeletonProps {
  readonly className?: string;
}

export function Skeleton({ className = "h-4 w-full" }: SkeletonProps) {
  return <div className={`animate-pulse rounded-md bg-slate-200 ${className}`} aria-hidden="true" />;
}

/** Kart görünümlü satır iskeleti (liste/inbox yüklenirken). */
export function SkeletonCard() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-3 w-1/3" />
        </div>
        <Skeleton className="h-6 w-20" />
      </div>
    </div>
  );
}
