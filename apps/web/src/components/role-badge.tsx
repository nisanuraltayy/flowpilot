/** Onay rolü rozeti (Ekip yöneticisi / Finans / Genel müdür). null → hiçbir şey. */

import { approvalRoleLabel } from "@/features/purchase-requests/display";

interface RoleBadgeProps {
  readonly role: string | null;
  readonly prefix?: string;
}

export function RoleBadge({ role, prefix }: RoleBadgeProps) {
  const label = approvalRoleLabel(role);
  if (label === null) {
    return null;
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-brand-200 bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-700">
      {prefix ? <span className="text-brand-400">{prefix}</span> : null}
      {label}
    </span>
  );
}
