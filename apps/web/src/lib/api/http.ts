/**
 * FlowPilot FastAPI için ortak, YALNIZ SERVER-SIDE istek yardımcısı.
 *
 * `server-only` import'u bu modülün client bundle'a sızmasını derleme anında
 * engeller. Bearer token yalnız burada iletilir; browser'a/log'a taşınmaz.
 *
 * Kurallar:
 * - Native fetch, `cache: "no-store"`, kontrollü timeout, otomatik retry YOK.
 * - HTTP durum kodları güvenli, kullanıcıya taşınabilir sonuçlara eşlenir.
 * - Backend teknik detayı (stack, teknik 422 dizisi) kullanıcıya SIZDIRILMAZ.
 */

import "server-only";

import { getApiBaseUrl } from "@/lib/env";

const REQUEST_TIMEOUT_MS = 10_000;
const GENERIC_VALIDATION_MESSAGE = "Girdiğiniz bilgiler geçersiz. Lütfen kontrol edin.";
const GENERIC_CONFLICT_MESSAGE = "Bu işlem şu anda tamamlanamadı (çakışma). Sayfayı yenileyin.";

/** İstek başarısızlığının kullanıcıya taşınabilir, güvenli sınıflandırması. */
export type ApiFailure =
  | { readonly kind: "unauthorized" }
  | { readonly kind: "forbidden" }
  | { readonly kind: "not_found" }
  | { readonly kind: "conflict"; readonly message: string }
  | { readonly kind: "gone" }
  | { readonly kind: "validation_error"; readonly message: string }
  | { readonly kind: "service_unavailable" }
  | { readonly kind: "server_error" }
  | { readonly kind: "network_error" };

/** Başarı → doğrulanmış veri; aksi hâlde güvenli failure. */
export type ApiOutcome<T> = { readonly kind: "ok"; readonly data: T } | ApiFailure;

type RawResult =
  | { readonly kind: "ok"; readonly json: unknown }
  | ApiFailure;

interface RequestOptions {
  readonly method: "GET" | "POST";
  readonly path: string;
  /** Bearer token — atlanırsa PUBLIC istek yapılır (Authorization header eklenmez). */
  readonly accessToken?: string;
  readonly body?: unknown;
  readonly extraHeaders?: Readonly<Record<string, string>>;
}

/**
 * Backend'in KULLANICI-DOSTU Türkçe `detail` string'ini taşır; FastAPI'nin
 * otomatik teknik 422 dizisi (loc/msg/type) KULLANICIYA GÖSTERİLMEZ.
 */
function extractDetailMessage(body: unknown, fallback: string): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof (body as { detail: unknown }).detail === "string"
  ) {
    return (body as { detail: string }).detail;
  }
  return fallback;
}

async function readJsonSafe(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/** Düşük seviye istek: Bearer ekler, durum kodlarını failure'lara eşler. */
export async function apiRequest(options: RequestOptions): Promise<RawResult> {
  const headers: Record<string, string> = { ...options.extraHeaders };
  // Bearer YALNIZ token verilmişse eklenir; public endpoint'ler (davet önizleme) token'sızdır.
  if (options.accessToken !== undefined) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${options.path}`, {
      method: options.method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    // Timeout / DNS / bağlantı reddi — token veya teknik detay taşınmaz.
    return { kind: "network_error" };
  }

  if (response.status >= 200 && response.status < 300) {
    return { kind: "ok", json: await readJsonSafe(response) };
  }
  if (response.status === 401) {
    return { kind: "unauthorized" };
  }
  if (response.status === 403) {
    return { kind: "forbidden" };
  }
  if (response.status === 404) {
    return { kind: "not_found" };
  }
  if (response.status === 409) {
    return {
      kind: "conflict",
      message: extractDetailMessage(await readJsonSafe(response), GENERIC_CONFLICT_MESSAGE),
    };
  }
  if (response.status === 410) {
    return { kind: "gone" };
  }
  if (response.status === 422) {
    return {
      kind: "validation_error",
      message: extractDetailMessage(await readJsonSafe(response), GENERIC_VALIDATION_MESSAGE),
    };
  }
  if (response.status === 503) {
    return { kind: "service_unavailable" };
  }
  return { kind: "server_error" };
}
