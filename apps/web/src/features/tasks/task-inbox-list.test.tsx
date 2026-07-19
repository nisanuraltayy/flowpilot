import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Gömülü karar formunun server action'ını stub'la (next/cache import etmeden).
vi.mock("@/features/tasks/actions", () => ({ decideApprovalTaskAction: async () => ({ status: "idle" }) }));

import { TaskInboxList } from "@/features/tasks/task-inbox-list";
import type { InboxItem } from "@/lib/api/resources";

const ITEMS: InboxItem[] = [
  {
    taskId: "tttttttt-tttt-4ttt-8ttt-tttttttttttt",
    purchaseRequestId: "pppppppp-pppp-4ppp-8ppp-pppppppppppp",
    purchaseRequestTitle: "Sunucu yenileme",
    amountMinor: 6_000_000,
    currency: "TRY",
    requiredRole: "finance",
    status: "active",
    workflowInstanceId: "iiiiiiii-iiii-4iii-8iii-iiiiiiiiiiii",
    createdAt: "2026-07-19T10:00:00Z",
    dueAt: null,
  },
];

describe("TaskInboxList", () => {
  it("görevi aktif adım olarak sunar: 'Sıra sende' bağlamı + başlık + tutar + karar butonları", () => {
    render(<TaskInboxList items={ITEMS} />);
    expect(screen.getByText("Sunucu yenileme")).toBeInTheDocument();
    expect(screen.getByText("60.000,00 ₺")).toBeInTheDocument();
    // "Sıra sende" bağlamı, görevin rolüyle birlikte.
    expect(screen.getByText("Sıra sende — Finans onayı")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Onayla/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reddet/ })).toBeInTheDocument();
  });

  it("talep detayına bağlantı verir; UUID görünür metinde yok", () => {
    const { container } = render(<TaskInboxList items={ITEMS} />);
    const link = screen.getByRole("link", { name: "Sunucu yenileme" });
    expect(link).toHaveAttribute("href", "/purchase-requests/pppppppp-pppp-4ppp-8ppp-pppppppppppp");
    expect(container.textContent).not.toContain("tttttttt-tttt-4ttt-8ttt-tttttttttttt");
  });
});
