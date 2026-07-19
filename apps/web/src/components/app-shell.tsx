/**
 * Authenticated uygulama kabuğu: marka + aktif organizasyon + navigasyon + çıkış.
 *
 * Navigasyon semantic <nav>; aktif bağlantı `aria-current="page"` ile işaretlenir
 * (yalnız renkle değil). Masaüstü ve mobilde kullanılabilir (yatay kaydırılabilir nav).
 */

import Link from "next/link";

import { FlowPilotLogo } from "@/components/flowpilot-logo";
import { signOutAction } from "@/features/auth/actions";

export type NavKey = "overview" | "new" | "requests" | "inbox";

interface NavItem {
  readonly key: NavKey;
  readonly href: string;
  readonly label: string;
}

const NAV_ITEMS: readonly NavItem[] = [
  { key: "overview", href: "/dashboard", label: "Genel Bakış" },
  { key: "new", href: "/purchase-requests/new", label: "Yeni Talep" },
  { key: "requests", href: "/purchase-requests", label: "Taleplerim" },
  { key: "inbox", href: "/tasks/inbox", label: "Onay Kutusu" },
];

interface AppShellProps {
  readonly userEmail: string | null;
  readonly organizationName: string;
  readonly activeNav: NavKey;
  readonly children: React.ReactNode;
}

export function AppShell({ userEmail, organizationName, activeNav, children }: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <FlowPilotLogo />
            <span aria-hidden="true" className="text-slate-300">
              /
            </span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-900">{organizationName}</span>
              <Link
                href="/organizations/select"
                className="rounded text-xs font-medium text-blue-600 underline-offset-2 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                Değiştir
              </Link>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {userEmail ? (
              <span className="hidden text-sm text-slate-600 sm:inline">{userEmail}</span>
            ) : null}
            <form action={signOutAction}>
              <button
                type="submit"
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                Çıkış yap
              </button>
            </form>
          </div>
        </div>
        <nav aria-label="Ana menü" className="mx-auto max-w-5xl px-2">
          <ul className="flex gap-1 overflow-x-auto">
            {NAV_ITEMS.map((item) => {
              const isActive = item.key === activeNav;
              return (
                <li key={item.key}>
                  <Link
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    className={`inline-flex whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                      isActive
                        ? "border-blue-600 text-blue-700"
                        : "border-transparent text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">{children}</main>
    </div>
  );
}
