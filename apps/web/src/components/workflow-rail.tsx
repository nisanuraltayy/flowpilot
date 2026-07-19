/**
 * FlowPilot workflow görsel dili — bağlı adımlar / ilerleyen akış.
 *
 * Durum yalnız RENKLE değil ikon + etiketle anlatılır:
 * - completed: yeşil düğüm + tik
 * - active:    amber halka + dolu nokta
 * - upcoming:  boş (slate) düğüm
 * - rejected:  kırmızı düğüm + çarpı
 *
 * Ağır SVG/canvas yok — CSS + küçük inline ikon. Mobilde dikey, sm+'da yatay;
 * hiçbir modda sayfayı yatay taşırmaz (yatay varyant kendi kutusunda kalır).
 */

import { CheckIcon, XIcon } from "@/components/icons";

export type WorkflowStepState = "completed" | "active" | "upcoming" | "rejected";

export interface WorkflowStepData {
  readonly key: string;
  readonly label: string;
  readonly sublabel?: string;
  readonly state: WorkflowStepState;
}

const NODE: Record<WorkflowStepState, string> = {
  completed: "bg-green-600 text-white border-green-600",
  active: "bg-amber-50 text-amber-600 border-amber-500",
  upcoming: "bg-white text-slate-300 border-slate-300",
  rejected: "bg-red-600 text-white border-red-600",
};

const LABEL: Record<WorkflowStepState, string> = {
  completed: "text-slate-900",
  active: "text-amber-800",
  upcoming: "text-slate-400",
  rejected: "text-red-800",
};

const CONNECTOR: Record<WorkflowStepState, string> = {
  completed: "bg-green-400",
  active: "bg-amber-300",
  upcoming: "bg-slate-200",
  rejected: "bg-red-300",
};

export function WorkflowNode({
  state,
  className = "h-8 w-8",
}: {
  readonly state: WorkflowStepState;
  readonly className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-full border-2 ${NODE[state]} ${className}`}
    >
      {state === "completed" ? (
        <CheckIcon className="h-4 w-4" />
      ) : state === "rejected" ? (
        <XIcon className="h-4 w-4" />
      ) : state === "active" ? (
        <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
      ) : (
        <span className="h-2 w-2 rounded-full bg-slate-200" />
      )}
    </span>
  );
}

/** Ekran okuyucu için durum metni (yalnız renk değil). */
const STATE_TEXT: Record<WorkflowStepState, string> = {
  completed: "tamamlandı",
  active: "sırada",
  upcoming: "bekliyor",
  rejected: "reddedildi",
};

interface WorkflowRailProps {
  readonly steps: readonly WorkflowStepData[];
  /** Erişilebilir başlık (görünmez). */
  readonly ariaLabel?: string;
}

export function WorkflowRail({ steps, ariaLabel = "Süreç akışı" }: WorkflowRailProps) {
  if (steps.length === 0) {
    return null;
  }
  return (
    <div aria-label={ariaLabel} role="group">
      {/* Yatay (sm+) */}
      <ol className="hidden items-start sm:flex">
        {steps.map((step, index) => (
          <li key={step.key} className="flex min-w-0 flex-1 items-start last:flex-none">
            <div className="flex flex-col items-center gap-1.5 px-1 text-center">
              <WorkflowNode state={step.state} />
              <span className={`max-w-[7.5rem] text-xs font-medium ${LABEL[step.state]}`}>
                {step.label}
                <span className="sr-only"> ({STATE_TEXT[step.state]})</span>
              </span>
              {step.sublabel ? (
                <span className="text-[11px] text-slate-400">{step.sublabel}</span>
              ) : null}
            </div>
            {index < steps.length - 1 ? (
              <span
                aria-hidden="true"
                className={`mt-4 h-0.5 flex-1 rounded ${CONNECTOR[steps[index + 1].state]}`}
              />
            ) : null}
          </li>
        ))}
      </ol>

      {/* Dikey (mobil) */}
      <ol className="flex flex-col sm:hidden">
        {steps.map((step, index) => (
          <li key={step.key} className="relative flex gap-3 pb-4 last:pb-0">
            {index < steps.length - 1 ? (
              <span
                aria-hidden="true"
                className={`absolute left-[15px] top-8 h-[calc(100%-1.5rem)] w-0.5 rounded ${CONNECTOR[steps[index + 1].state]}`}
              />
            ) : null}
            <WorkflowNode state={step.state} />
            <div className="pt-1">
              <p className={`text-sm font-medium ${LABEL[step.state]}`}>
                {step.label}
                <span className="sr-only"> ({STATE_TEXT[step.state]})</span>
              </p>
              {step.sublabel ? <p className="text-xs text-slate-400">{step.sublabel}</p> : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
