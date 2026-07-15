/**
 * Organization form şeması — backend `OrganizationName` kurallarıyla hizalı:
 * boş/whitespace-only reddedilir, üst sınır 200. NİHAİ doğrulama kaynağı
 * HER ZAMAN backend'dir; buradaki şema yalnız hızlı kullanıcı geri bildirimi
 * içindir.
 */

import { z } from "zod";

export const ORGANIZATION_NAME_MAX_LENGTH = 200;

export const organizationNameSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Organizasyon adı boş olamaz.")
    .max(
      ORGANIZATION_NAME_MAX_LENGTH,
      `Organizasyon adı en fazla ${ORGANIZATION_NAME_MAX_LENGTH} karakter olabilir.`,
    ),
});

export type OrganizationNameInput = z.infer<typeof organizationNameSchema>;
