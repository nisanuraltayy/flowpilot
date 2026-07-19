import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Timeline } from "@/components/timeline";
import type { TimelineItem } from "@/lib/api/resources";

const ITEMS: TimelineItem[] = [
  {
    eventType: "purchase_request.created",
    occurredAt: "2026-07-19T09:00:00Z",
    actorIsCurrentUser: true,
    roleKey: null,
    taskId: null,
    message: "Satın alma talebi oluşturuldu.",
  },
  {
    eventType: "approval.approved",
    occurredAt: "2026-07-19T09:05:00Z",
    actorIsCurrentUser: false,
    roleKey: "finance",
    taskId: "xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx",
    message: "Onay adımı onaylandı.",
  },
  {
    eventType: "some.unknown.event",
    occurredAt: "2026-07-19T09:06:00Z",
    actorIsCurrentUser: false,
    roleKey: null,
    taskId: null,
    message: "Bilinmeyen olay.",
  },
];

describe("Timeline", () => {
  it("event türlerini Türkçe etiketle gösterir", () => {
    render(<Timeline items={ITEMS} />);
    expect(screen.getByText("Talep oluşturuldu")).toBeInTheDocument();
    expect(screen.getByText("Talep adımı onaylandı")).toBeInTheDocument();
  });

  it("current user olayında 'Sen', rolde RoleBadge gösterir", () => {
    render(<Timeline items={ITEMS} />);
    expect(screen.getByText("Sen")).toBeInTheDocument();
    expect(screen.getByText("Finans")).toBeInTheDocument();
  });

  it("bilinmeyen event türünü ham gösterir (fallback)", () => {
    render(<Timeline items={ITEMS} />);
    expect(screen.getByText("some.unknown.event")).toBeInTheDocument();
  });

  it("ham metadata/UUID görünür metinde gösterilmez", () => {
    const { container } = render(<Timeline items={ITEMS} />);
    expect(container.textContent).not.toContain("xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx");
  });

  it("boş timeline güvenli mesaj gösterir", () => {
    render(<Timeline items={[]} />);
    expect(screen.getByText("Henüz bir olay yok.")).toBeInTheDocument();
  });
});
