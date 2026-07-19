/** Etiket eşlemeleri — bilinen değerler Türkçe; bilinmeyen değer güvenli fallback. */

import { describe, expect, it } from "vitest";

import {
  approvalRoleLabel,
  purchaseRequestStatusLabel,
  purchaseRequestStatusTone,
  timelineEventLabel,
} from "@/features/purchase-requests/display";

describe("purchaseRequestStatusLabel", () => {
  it("bilinen durumları Türkçeye çevirir", () => {
    expect(purchaseRequestStatusLabel("draft")).toBe("Taslak");
    expect(purchaseRequestStatusLabel("in_approval")).toBe("Onay bekliyor");
    expect(purchaseRequestStatusLabel("approved")).toBe("Onaylandı");
    expect(purchaseRequestStatusLabel("rejected")).toBe("Reddedildi");
  });

  it("bilinmeyen durumu UYDURMAZ (ham değeri döner)", () => {
    expect(purchaseRequestStatusLabel("mystery_status")).toBe("mystery_status");
  });
});

describe("purchaseRequestStatusTone", () => {
  it("durumları rozet tonuna eşler", () => {
    expect(purchaseRequestStatusTone("approved")).toBe("success");
    expect(purchaseRequestStatusTone("rejected")).toBe("error");
    expect(purchaseRequestStatusTone("in_approval")).toBe("pending");
    expect(purchaseRequestStatusTone("draft")).toBe("neutral");
    expect(purchaseRequestStatusTone("unknown")).toBe("neutral");
  });
});

describe("approvalRoleLabel", () => {
  it("rolleri Türkçeye çevirir", () => {
    expect(approvalRoleLabel("team_manager")).toBe("Ekip yöneticisi");
    expect(approvalRoleLabel("finance")).toBe("Finans");
    expect(approvalRoleLabel("general_manager")).toBe("Genel müdür");
  });

  it("null → null; bilinmeyen rol ham döner", () => {
    expect(approvalRoleLabel(null)).toBeNull();
    expect(approvalRoleLabel("cfo")).toBe("cfo");
  });
});

describe("timelineEventLabel", () => {
  it("bilinen event türlerini Türkçeye çevirir", () => {
    expect(timelineEventLabel("purchase_request.created")).toBe("Talep oluşturuldu");
    expect(timelineEventLabel("workflow.completed")).toBe("Onay süreci tamamlandı");
    expect(timelineEventLabel("approval.task_assigned")).toBe("Onay görevi atandı");
  });

  it("bilinmeyen event türünü güvenli biçimde ham döner", () => {
    expect(timelineEventLabel("some.new.event")).toBe("some.new.event");
  });
});
