/**
 * Süreç zaman çizelgesi — append-only audit olayları, kronolojik.
 *
 * Event türü Türkçe etikete eşlenir; bilinmeyen tür güvenli fallback ile gösterilir.
 * metadata KÖR RENDER EDİLMEZ; UUID ana arayüzde gösterilmez.
 */

import {
  approvalRoleLabel,
  timelineEventLabel,
} from "@/features/purchase-requests/display";
import { formatDateTime } from "@/lib/datetime";
import type { TimelineItem as TimelineItemData } from "@/lib/api/resources";

function TimelineItem({ item }: { readonly item: TimelineItemData }) {
  const role = approvalRoleLabel(item.roleKey);
  return (
    <li className="relative pl-6">
      <span
        aria-hidden="true"
        className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full border-2 border-blue-500 bg-white"
      />
      <p className="text-sm font-medium text-slate-900">{timelineEventLabel(item.eventType)}</p>
      <p className="text-sm text-slate-600">{item.message}</p>
      <p className="mt-0.5 text-xs text-slate-400">
        <time dateTime={item.occurredAt}>{formatDateTime(item.occurredAt)}</time>
        {role ? <span> · {role}</span> : null}
        {item.actorIsCurrentUser ? <span> · Sen</span> : null}
      </p>
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
    <ol className="flex flex-col gap-4 border-l border-slate-200 pl-2">
      {items.map((item, index) => (
        <TimelineItem key={`${item.eventType}-${item.occurredAt}-${index}`} item={item} />
      ))}
    </ol>
  );
}
