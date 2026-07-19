/** Aktif organizasyon göstergesi + "Değiştir" bağlantısı (org adı; UUID gösterilmez). */

import Link from "next/link";

import { BuildingIcon } from "@/components/icons";

interface OrganizationSwitcherProps {
  readonly organizationName: string;
}

export function OrganizationSwitcher({ organizationName }: OrganizationSwitcherProps) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2.5">
      <div className="flex items-center gap-2">
        <BuildingIcon className="h-4 w-4 shrink-0 text-brand-200" />
        <span className="truncate text-sm font-medium text-white" title={organizationName}>
          {organizationName}
        </span>
      </div>
      <Link
        href="/organizations/select"
        className="mt-1 inline-block rounded text-xs font-medium text-brand-200 underline-offset-2 hover:text-white hover:underline"
      >
        Organizasyon değiştir
      </Link>
    </div>
  );
}
