/**
 * Süreç zaman çizelgesi — append-only audit olayları, kronolojik.
 *
 * Event türü Türkçe etikete + ikona + tona eşlenir; bilinmeyen tür güvenli fallback
 * (nötr). metadata KÖR RENDER EDİLMEZ; UUID ana arayüzde gösterilmez.
 */

import type { ComponentType } from "react";

import { CheckIcon, DocumentsIcon, InboxIcon, OverviewIcon, XIcon } from "@/components/icons";
import { RoleBadge } from "@/components/role-badge";
import { approvalRoleLabel, timelineEventLabel } from "@/features/purchase-requests/display";
import { formatDateTime } from "@/lib/datetime";
import type { TimelineItem as TimelineItemData } from "@/lib/api/resources";

type EventTone = "neutral" | "brand" | "success" | "danger";

const EVENT_STYLE: Record<
  string,
  { readonly tone: EventTone; readonly Icon: ComponentType<{ className?: string }> }
> = {
  "purchase_request.created": { tone: "neutral", Icon: DocumentsIcon },
  "workflow.started": { tone: "brand", Icon: OverviewIcon },
  "approval.task_assigned": { tone: "brand", Icon: InboxIcon },
  "approval.approved": { tone: "success", Icon: CheckIcon },
  "approval.rejected": { tone: "danger", Icon: XIcon },
  "workflow.completed": { tone: "success", Icon: CheckIcon },
  "workflow.rejected": { tone: "danger", Icon: XIcon },
};

const DOT_TONE: Record<EventTone, string> = {
  neutral: "border-slate-300 bg-white text-slate-500",
  brand: "border-brand-300 bg-brand-50 text-brand-600",
  success: "border-green-300 bg-green-50 text-green-600",
  danger: "border-red-300 bg-red-50 text-red-600",
};

function TimelineItem({ item, isLast }: { readonly item: TimelineItemData; readonly isLast: boolean }) {
  const style = EVENT_STYLE[item.eventType] ?? { tone: "neutral" as const, Icon: DocumentsIcon };
  const role = approvalRoleLabel(item.roleKey);

  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {/* Dikey çizgi */}
      {isLast ? null : (
        <span aria-hidden="true" className="absolute left-[15px] top-8 h-[calc(100%-1.5rem)] w-px bg-slate-200" />
      )}
      {/* İkon noktası */}
      <span
        aria-hidden="true"
        className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border ${DOT_TONE[style.tone]}`}
      >
        <style.Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-slate-900">{timelineEventLabel(item.eventType)}</p>
          {role ? <RoleBadge role={item.roleKey} /> : null}
          {item.actorIsCurrentUser ? (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              Sen
            </span>
          ) : null}
        </div>
        <p className="mt-0.5 text-sm text-slate-600">{item.message}</p>
        <time dateTime={item.occurredAt} className="mt-0.5 block text-xs text-slate-400">
          {formatDateTime(item.occurredAt)}
        </time>
      </div>
    </li>
  );
}

interface TimelineProps {
  readonly items: readonly TimelineItemData[];
}

export function Timeline({ items }: TimelineProps) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-500">Henüz bir olay yok.</p>;
  }
  return (
    <ol className="flex flex-col">
      {items.map((item, index) => (
        <TimelineItem
          key={`${item.eventType}-${item.occurredAt}-${index}`}
          item={item}
          isLast={index === items.length - 1}
        />
      ))}
    </ol>
  );
}
