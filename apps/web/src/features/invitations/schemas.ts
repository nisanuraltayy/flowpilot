/**
 * Davet oluşturma formu doğrulaması (istemci-yakın). NİHAİ kaynak backend'dir;
 * bu şema yalnız hızlı geri bildirim + yanlış tip göndermeyi önlemek içindir.
 */

import { z } from "zod";

export const invitationRoleSchema = z.enum(["admin", "member"]);

export const createInvitationSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "E-posta gerekli.")
    .email("Geçerli bir e-posta adresi girin."),
  role: invitationRoleSchema,
});

export type CreateInvitationFormValues = z.infer<typeof createInvitationSchema>;
