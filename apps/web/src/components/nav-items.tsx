/** Ana navigasyon tanımı — sidebar + mobil menü + testler için TEK kaynak. */

import type { ComponentType } from "react";

import { DocumentsIcon, InboxIcon, OverviewIcon, PlusIcon } from "@/components/icons";

export type NavKey = "overview" | "new" | "requests" | "inbox";

export interface NavItem {
  readonly key: NavKey;
  readonly href: string;
  readonly label: string;
  readonly Icon: ComponentType<{ readonly className?: string }>;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { key: "overview", href: "/dashboard", label: "Genel Bakış", Icon: OverviewIcon },
  { key: "new", href: "/purchase-requests/new", label: "Yeni Talep", Icon: PlusIcon },
  { key: "requests", href: "/purchase-requests", label: "Taleplerim", Icon: DocumentsIcon },
  { key: "inbox", href: "/tasks/inbox", label: "Onay Kutusu", Icon: InboxIcon },
];
