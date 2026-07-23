/**
 * Uygulama kenar çubuğu içeriği (koyu lacivert). Hem masaüstü sabit sidebar'da
 * HEM de mobil menü çekmecesinde AYNI içerik gösterilir.
 *
 * Semantic <nav>; aktif bağlantı `aria-current="page"` + görsel vurgu (yalnız renk
 * değil: sol kenar + arka plan + kalın metin). Çıkış server-action formudur.
 */

import Link from "next/link";

import { FlowPilotLogo } from "@/components/flowpilot-logo";
import { type NavKey, visibleNavItems } from "@/components/nav-items";
import { OrganizationSwitcher } from "@/components/organization-switcher";
import { signOutAction } from "@/features/auth/actions";

interface AppSidebarProps {
  readonly userEmail: string | null;
  readonly organizationName: string;
  readonly activeNav: NavKey;
  /** owner/admin ise yönetim (Davetler) bağlantısı gösterilir. */
  readonly canManage?: boolean;
}

export function AppSidebar({
  userEmail,
  organizationName,
  activeNav,
  canManage = false,
}: AppSidebarProps) {
  const items = visibleNavItems(canManage);
  return (
    <div className="flex h-full flex-col gap-6 bg-brand-900 px-4 py-5 text-white">
      <div className="px-1">
        <FlowPilotLogo onDark />
      </div>

      <OrganizationSwitcher organizationName={organizationName} />

      <nav aria-label="Ana menü" className="flex-1">
        <ul className="flex flex-col gap-1">
          {items.map((item) => {
            const isActive = item.key === activeNav;
            return (
              <li key={item.key}>
                <Link
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                  className={`flex items-center gap-3 rounded-lg border-l-2 px-3 py-2.5 text-sm transition-colors ${
                    isActive
                      ? "border-white bg-white/10 font-semibold text-white"
                      : "border-transparent font-medium text-brand-100/80 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <item.Icon className="h-5 w-5 shrink-0" />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-white/10 pt-4">
        {userEmail ? (
          <div className="mb-2 px-1">
            <p className="text-[10px] font-medium uppercase tracking-wide text-brand-300/80">
              Oturum
            </p>
            <p className="truncate text-xs text-brand-100" title={userEmail}>
              {userEmail}
            </p>
          </div>
        ) : null}
        <form action={signOutAction}>
          <button
            type="submit"
            className="w-full rounded-lg border border-white/15 px-3 py-2 text-sm font-medium text-brand-100 transition-colors hover:bg-white/5 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
          >
            Çıkış yap
          </button>
        </form>
      </div>
    </div>
  );
}
