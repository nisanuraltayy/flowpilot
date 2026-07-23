/** Ana navigasyon tanımı — sidebar + mobil menü + testler için TEK kaynak. */

import type { ComponentType } from "react";

import { DocumentsIcon, InboxIcon, OverviewIcon, PlusIcon, UsersIcon } from "@/components/icons";

export type NavKey = "overview" | "new" | "requests" | "inbox" | "invitations";

export interface NavItem {
  readonly key: NavKey;
  readonly href: string;
  readonly label: string;
  readonly Icon: ComponentType<{ readonly className?: string }>;
  /** Yalnız owner/admin görür (davet/üye yönetimi). Frontend görünürlüğü UX içindir. */
  readonly requiresManage?: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { key: "overview", href: "/dashboard", label: "Genel Bakış", Icon: OverviewIcon },
  { key: "new", href: "/purchase-requests/new", label: "Yeni Talep", Icon: PlusIcon },
  { key: "requests", href: "/purchase-requests", label: "Taleplerim", Icon: DocumentsIcon },
  { key: "inbox", href: "/tasks/inbox", label: "Onay Kutusu", Icon: InboxIcon },
  {
    key: "invitations",
    href: "/settings/team/invitations",
    label: "Davetler",
    Icon: UsersIcon,
    requiresManage: true,
  },
];

/** Rol görünürlüğüne göre gösterilecek nav öğeleri. */
export function visibleNavItems(canManage: boolean): readonly NavItem[] {
  return NAV_ITEMS.filter((item) => !item.requiresManage || canManage);
}
