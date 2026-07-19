"use client";

/**
 * Mobil navigasyon — üst çubuk + erişilebilir çekmece (drawer).
 *
 * - Menü butonu `aria-expanded` + `aria-controls`.
 * - Açılınca kapat butonuna odak; Escape ile kapanır; kapanınca odak tetikleyiciye döner.
 * - Route değişince otomatik kapanır (link tıklaması sonrası).
 * - İçerik (sidebar) `children` olarak SERVER'dan gelir; drawer client, içerik server.
 * - Ekranı taşırmaz: panel genişliği sınırlı, overlay tıklaması kapatır.
 */

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { FlowPilotLogo } from "@/components/flowpilot-logo";
import { MenuIcon, XIcon } from "@/components/icons";

interface MobileNavProps {
  readonly children: React.ReactNode;
}

export function MobileNav({ children }: MobileNavProps) {
  const pathname = usePathname();
  // Çekmece YALNIZ açıldığı route'ta açık kalır: pathname değişince (link tıklaması)
  // türetilmiş `open` otomatik false olur — effect içinde setState yok.
  const [openPath, setOpenPath] = useState<string | null>(null);
  const open = openPath === pathname;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const close = () => setOpenPath(null);

  // Açık durumda: kapat butonuna odak + Escape ile kapatma.
  useEffect(() => {
    if (!open) {
      return;
    }
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="lg:hidden">
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <FlowPilotLogo />
        <button
          ref={triggerRef}
          type="button"
          onClick={() => setOpenPath(pathname)}
          aria-label="Menüyü aç"
          aria-expanded={open}
          aria-controls="mobile-nav-panel"
          className="rounded-lg p-2 text-slate-700 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          <MenuIcon />
        </button>
      </div>

      {open ? (
        <div
          className="fixed inset-0 z-40"
          role="dialog"
          aria-modal="true"
          aria-label="Menü"
        >
          <button
            type="button"
            aria-label="Menüyü kapat"
            tabIndex={-1}
            onClick={close}
            className="absolute inset-0 h-full w-full cursor-default bg-slate-900/50"
          />
          <div
            id="mobile-nav-panel"
            className="absolute inset-y-0 left-0 w-72 max-w-[85%] overflow-y-auto shadow-2xl"
          >
            <button
              ref={closeRef}
              type="button"
              onClick={() => {
                close();
                triggerRef.current?.focus();
              }}
              aria-label="Menüyü kapat"
              className="absolute right-2 top-2 z-10 rounded-lg p-2 text-brand-100 hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
            >
              <XIcon />
            </button>
            {children}
          </div>
        </div>
      ) : null}
    </div>
  );
}
