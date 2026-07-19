import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PurchaseRequestList } from "@/features/purchase-requests/purchase-request-list";
import type { PurchaseRequestListItem } from "@/lib/api/resources";

const ITEMS: PurchaseRequestListItem[] = [
  {
    purchaseRequestId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    title: "Dizüstü bilgisayar",
    amountMinor: 1_250_050,
    currency: "TRY",
    status: "in_approval",
    currentApprovalRole: "team_manager",
    createdAt: "2026-07-19T09:00:00Z",
    updatedAt: "2026-07-19T09:00:00Z",
  },
];

describe("PurchaseRequestList", () => {
  it("başlık, tutar (TL), durum ve rolü gösterir", () => {
    render(<PurchaseRequestList items={ITEMS} />);
    // Masaüstü tablo + mobil kart aynı DOM'da olduğundan getAllByText.
    expect(screen.getAllByText("Dizüstü bilgisayar").length).toBeGreaterThan(0);
    expect(screen.getAllByText("12.500,50 ₺").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Onay bekliyor").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Ekip yöneticisi").length).toBeGreaterThan(0);
  });

  it("detay bağlantısı doğru talebe gider", () => {
    render(<PurchaseRequestList items={ITEMS} />);
    const links = screen.getAllByRole("link");
    expect(
      links.some((l) => l.getAttribute("href") === "/purchase-requests/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    ).toBe(true);
  });

  it("UUID görünür metinde gösterilmez", () => {
    const { container } = render(<PurchaseRequestList items={ITEMS} />);
    expect(container.textContent).not.toContain("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
  });
});
