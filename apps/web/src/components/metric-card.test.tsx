import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DocumentsIcon } from "@/components/icons";
import { MetricCard } from "@/components/metric-card";

describe("MetricCard", () => {
  it("etiketi ve GERÇEK sayısal değeri gösterir", () => {
    render(<MetricCard label="Taleplerim" value={3} tone="brand" Icon={DocumentsIcon} />);
    expect(screen.getByText("Taleplerim")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("sıfır değeri de gösterir (sahte sayı üretmez)", () => {
    render(<MetricCard label="Bekleyen onay görevi" value={0} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
