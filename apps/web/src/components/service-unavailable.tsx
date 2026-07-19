/** API'ye erişilemediğinde gösterilen güvenli, kullanıcı-dostu durum. */

import Link from "next/link";

interface ServiceUnavailableProps {
  readonly retryHref: string;
}

export function ServiceUnavailable({ retryHref }: ServiceUnavailableProps) {
  return (
    <div
      role="status"
      className="flex min-h-screen flex-col items-center justify-center gap-3 px-4 text-center"
    >
      <h1 className="text-lg font-semibold text-slate-900">Servise şu anda erişilemiyor</h1>
      <p className="max-w-sm text-sm text-slate-600">
        Sunucuya ulaşılamıyor. Lütfen birkaç dakika sonra tekrar deneyin.
      </p>
      <Link
        href={retryHref}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
      >
        Tekrar dene
      </Link>
    </div>
  );
}
