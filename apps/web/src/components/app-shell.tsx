/**
 * Authenticated uygulama kabuğu — masaüstünde sabit sol sidebar, mobilde üst çubuk +
 * erişilebilir çekmece. Aynı sidebar içeriği her iki modda paylaşılır.
 */

import { AppSidebar } from "@/components/app-sidebar";
import { MobileNav } from "@/components/mobile-nav";
import type { NavKey } from "@/components/nav-items";

export type { NavKey } from "@/components/nav-items";

interface AppShellProps {
  readonly userEmail: string | null;
  readonly organizationName: string;
  readonly activeNav: NavKey;
  /** owner/admin ise yönetim (Davetler) bağlantısı gösterilir (UX; backend esas). */
  readonly canManage?: boolean;
  readonly children: React.ReactNode;
}

export function AppShell({
  userEmail,
  organizationName,
  activeNav,
  canManage = false,
  children,
}: AppShellProps) {
  const sidebar = (
    <AppSidebar
      userEmail={userEmail}
      organizationName={organizationName}
      activeNav={activeNav}
      canManage={canManage}
    />
  );

  return (
    <div className="min-h-screen bg-canvas">
      {/* Masaüstü: sabit sol sidebar */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 lg:block">{sidebar}</aside>

      {/* Mobil: üst çubuk + çekmece (aynı sidebar içeriği) */}
      <MobileNav>{sidebar}</MobileNav>

      {/* İçerik alanı */}
      <div className="lg:pl-64">
        <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 lg:py-10">{children}</main>
      </div>
    </div>
  );
}
