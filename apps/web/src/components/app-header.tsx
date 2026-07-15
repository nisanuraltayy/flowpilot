/**
 * Authenticated uygulama üst çubuğu — marka, kullanıcı e-postası ve çıkış.
 * Çıkış, signOutAction'a bağlı bir server-action formudur.
 */

import { signOutAction } from "@/features/auth/actions";
import { FlowPilotLogo } from "@/components/flowpilot-logo";

interface AppHeaderProps {
  readonly userEmail: string | null;
}

export function AppHeader({ userEmail }: AppHeaderProps) {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <FlowPilotLogo />
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
    </header>
  );
}
