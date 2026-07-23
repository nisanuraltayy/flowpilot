/**
 * CreateInvitationForm testleri — fake action; gerçek backend YOK.
 *
 * Güvenlik odak: davet URL'si (ham token içerir) YALNIZ başarı modalı AÇIKKEN görünür;
 * modal kapanınca DOM'dan kalkar. Rol seçiminde owner/Sahip YOKTUR.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import type { CreateInvitationResult } from "@/features/invitations/actions";
import { CreateInvitationForm } from "@/features/invitations/create-invitation-form";

const INVITE_URL = "https://app.example.com/invitations/accept?org=1&token=raw-token-marker";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Deterministik, artan UUID üreteci (gerçek rastgele değere bağlanmadan). */
function seqGen(): () => string {
  let n = 0;
  return () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`;
}

/** Gönderilen Idempotency-Key'leri kaydeden fake action. */
function recording(next: () => CreateInvitationResult) {
  const keys: (string | null)[] = [];
  const action = async (
    _previous: CreateInvitationResult,
    formData: FormData,
  ): Promise<CreateInvitationResult> => {
    const raw = formData.get("idempotencyKey");
    keys.push(typeof raw === "string" && raw !== "" ? raw : null);
    return next();
  };
  return { action, keys };
}

async function retypeEmail(user: ReturnType<typeof userEvent.setup>, value: string) {
  // React 19 hata sonrası uncontrolled alanı sıfırlar → retry'da yeniden yazılır (gerçek akış).
  const input = screen.getByLabelText("E-posta");
  await user.clear(input);
  await user.type(input, value);
}

function succeeding(
  overrides: { duplicate?: boolean; inviteUrl?: string | null } = {},
): () => Promise<CreateInvitationResult> {
  return async () => ({
    status: "success",
    invitedEmail: "davetli@sirket.com",
    role: "admin",
    expiresAt: "2026-07-30T00:00:00Z",
    duplicate: false,
    inviteUrl: INVITE_URL,
    ...overrides,
  });
}

function failing(message: string, fieldErrors?: Record<string, string[]>): () => Promise<CreateInvitationResult> {
  return async () => ({ status: "error", message, fieldErrors });
}

async function submit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("E-posta"), "davetli@sirket.com");
  await user.click(screen.getByRole("button", { name: "Davet oluştur" }));
}

describe("CreateInvitationForm", () => {
  it("e-posta alanı ve rol seçimini (Üye/Yönetici) render eder; Sahip yok", () => {
    render(<CreateInvitationForm action={failing("x")} />);

    expect(screen.getByLabelText("E-posta")).toBeInTheDocument();
    const roleSelect = screen.getByLabelText("Rol");
    const options = within(roleSelect).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Üye", "Yönetici"]);
    expect(options).not.toContain("Sahip");
  });

  it("başarıda davet URL'sini modalda bir kez gösterir; kapanınca token DOM'dan kalkar", async () => {
    const user = userEvent.setup();
    const { container } = render(<CreateInvitationForm action={succeeding()} />);

    await submit(user);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(INVITE_URL)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Bağlantıyı kopyala" })).toBeInTheDocument();

    // Modalı kapat → token'lı URL artık DOM'da değil (× ve "Kapat" aynı erişilebilir ada sahip).
    await user.click(within(dialog).getAllByRole("button", { name: "Kapat" })[0]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(container.textContent).not.toContain("raw-token-marker");
  });

  it("idempotent replay (duplicate, url yok) güvenli bilgi mesajı gösterir, token göstermez", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <CreateInvitationForm action={succeeding({ duplicate: true, inviteUrl: null })} />,
    );

    await submit(user);

    expect(
      await screen.findByText(/zaten bekleyen bir davet var/i),
    ).toBeInTheDocument();
    expect(container.textContent).not.toContain("raw-token-marker");
  });

  it("alan hatasını server action'dan gösterir", async () => {
    const user = userEvent.setup();
    render(
      <CreateInvitationForm action={failing("Lütfen alanları kontrol edin.", { email: ["Geçerli bir e-posta girin."] })} />,
    );

    await submit(user);
    expect(await screen.findByText("Geçerli bir e-posta girin.")).toBeInTheDocument();
  });
});

describe("CreateInvitationForm — Idempotency-Key yaşam döngüsü", () => {
  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  const anError = (): CreateInvitationResult => ({ status: "error", message: "geçici" });
  const aSuccess = (): CreateInvitationResult => ({
    status: "success",
    invitedEmail: "a@b.com",
    role: "member",
    expiresAt: "2026-07-30T00:00:00Z",
    duplicate: false,
    inviteUrl: INVITE_URL,
  });

  it("ilk submit bir UUID key üretir", async () => {
    const user = userEvent.setup();
    const { action, keys } = recording(anError);
    render(<CreateInvitationForm action={action} generateIdempotencyKey={seqGen()} />);

    await user.type(screen.getByLabelText("E-posta"), "a@b.com");
    await user.click(screen.getByRole("button", { name: "Davet oluştur" }));

    expect(keys).toHaveLength(1);
    expect(keys[0]).toMatch(UUID_RE);
  });

  it("aynı payload retry'ında AYNI key kullanılır (alan sıfırlansa da)", async () => {
    const user = userEvent.setup();
    const { action, keys } = recording(anError);
    render(<CreateInvitationForm action={action} generateIdempotencyKey={seqGen()} />);

    await retypeEmail(user, "a@b.com");
    await user.click(screen.getByRole("button", { name: "Davet oluştur" }));
    await screen.findByRole("alert");
    // Hata sonrası React alanı sıfırlar; kullanıcı aynı e-postayı yeniden yazıp retry eder.
    await retypeEmail(user, "a@b.com");
    await user.click(screen.getByRole("button", { name: "Davet oluştur" }));

    expect(keys).toHaveLength(2);
    expect(keys[0]).toMatch(UUID_RE);
    expect(keys[1]).toBe(keys[0]);
  });

  it("e-posta değişirse yeni key üretilir", async () => {
    const user = userEvent.setup();
    const { action, keys } = recording(anError);
    render(<CreateInvitationForm action={action} generateIdempotencyKey={seqGen()} />);

    await retypeEmail(user, "a@b.com");
    await user.click(screen.getByRole("button", { name: "Davet oluştur" }));
    await screen.findByRole("alert");
    await retypeEmail(user, "farkli@b.com");
    await user.click(screen.getByRole("button", { name: "Davet oluştur" }));

    expect(keys).toHaveLength(2);
    expect(keys[1]).not.toBe(keys[0]);
  });

  it("rol değişirse yeni key üretilir", async () => {
    const user = userEvent.setup();
    const { action, keys } = recording(anError);
    render(<CreateInvitationForm action={action} generateIdempotencyKey={seqGen()} />);

    await retypeEmail(user, "a@b.com");
    await user.click(screen.getByRole("button", { name: "Davet oluştur" }));
    await screen.findByRole("alert");
    await retypeEmail(user, "a@b.com");
    await user.selectOptions(screen.getByLabelText("Rol"), "admin");
    await user.click(screen.getByRole("button", { name: "Davet oluştur" }));

    expect(keys).toHaveLength(2);
    expect(keys[1]).not.toBe(keys[0]);
  });

  it("başarılı işlemden (modal kapanınca) sonraki yeni submit yeni key kullanır", async () => {
    const user = userEvent.setup();
    const { action, keys } = recording(aSuccess);
    render(<CreateInvitationForm action={action} generateIdempotencyKey={seqGen()} />);

    await retypeEmail(user, "a@b.com");
    await user.click(screen.getByRole("button", { name: "Davet oluştur" }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getAllByRole("button", { name: "Kapat" })[0]);

    await retypeEmail(user, "a@b.com");
    await user.click(screen.getByRole("button", { name: "Davet oluştur" }));

    expect(keys).toHaveLength(2);
    expect(keys[1]).not.toBe(keys[0]);
  });

  it("key browser storage'a yazılmaz", async () => {
    const user = userEvent.setup();
    const { action, keys } = recording(anError);
    render(<CreateInvitationForm action={action} generateIdempotencyKey={seqGen()} />);

    await user.type(screen.getByLabelText("E-posta"), "a@b.com");
    await user.click(screen.getByRole("button", { name: "Davet oluştur" }));

    const key = keys[0] ?? "";
    expect(key).toMatch(UUID_RE);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(document.cookie).not.toContain(key);
  });
});
