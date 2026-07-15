/**
 * Open-redirect koruması: yalnız uygulama içi, "/" ile başlayan yollara izin
 * verilir. Dış URL'ler, protokol-göreli (`//evil.com`) ve backslash hileleri
 * güvenli varsayılana düşer.
 */

const DEFAULT_AFTER_AUTH = "/onboarding/organization";

export function sanitizeInternalPath(
  candidate: string | null | undefined,
  fallback: string = DEFAULT_AFTER_AUTH,
): string {
  if (!candidate) {
    return fallback;
  }
  if (!candidate.startsWith("/")) {
    return fallback;
  }
  // "//host" ve "/\host" protokol-göreli dış yönlendirmelerdir.
  if (candidate.startsWith("//") || candidate.startsWith("/\\")) {
    return fallback;
  }
  return candidate;
}
