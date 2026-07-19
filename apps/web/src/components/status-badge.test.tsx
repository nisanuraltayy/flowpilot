import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/status-badge";

describe("StatusBadge", () => {
  it("bilinen durumları Türkçe etiketle gösterir (yalnız renk değil)", () => {
    render(<StatusBadge status="in_approval" />);
    expect(screen.getByText("Onay bekliyor")).toBeInTheDocument();
  });

  it("approved/rejected doğru etiketlenir", () => {
    const { rerender } = render(<StatusBadge status="approved" />);
    expect(screen.getByText("Onaylandı")).toBeInTheDocument();
    rerender(<StatusBadge status="rejected" />);
    expect(screen.getByText("Reddedildi")).toBeInTheDocument();
  });

  it("bilinmeyen durumu ham gösterir (uydurmaz)", () => {
    render(<StatusBadge status="mystery" />);
    expect(screen.getByText("mystery")).toBeInTheDocument();
  });
});
