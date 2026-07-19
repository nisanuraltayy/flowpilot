/** Tutarlı yükleniyor durumu (route `loading.tsx`'leri için). Erişilebilir duyuru içerir. */

import { Skeleton, SkeletonCard } from "@/components/skeleton";

interface LoadingStateProps {
  readonly rows?: number;
}

export function LoadingState({ rows = 3 }: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:pl-72"
    >
      <span className="sr-only">Yükleniyor…</span>
      <Skeleton className="h-8 w-56" />
      <div className="mt-6 flex flex-col gap-3">
        {Array.from({ length: rows }).map((_, index) => (
          <SkeletonCard key={index} />
        ))}
      </div>
    </div>
  );
}
