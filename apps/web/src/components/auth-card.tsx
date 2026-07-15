/**
 * Auth ve onboarding ekranlarının ortak kart düzeni — marka + başlık + içerik.
 * Login ve onboarding aynı görsel dili paylaşır.
 */

import { FlowPilotLogo } from "@/components/flowpilot-logo";

interface AuthCardProps {
  readonly title: string;
  readonly subtitle?: string;
  readonly children: React.ReactNode;
}

export function AuthCard({ title, subtitle, children }: AuthCardProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex justify-center">
          <FlowPilotLogo />
        </div>
        <section
          aria-labelledby="auth-card-title"
          className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm"
        >
          <h1 id="auth-card-title" className="text-xl font-semibold text-slate-900">
            {title}
          </h1>
          {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
          <div className="mt-6">{children}</div>
        </section>
      </div>
    </main>
  );
}
