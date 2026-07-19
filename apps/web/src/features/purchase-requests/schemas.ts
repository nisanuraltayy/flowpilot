import { z } from "zod";

export const TITLE_MAX_LENGTH = 200;
export const DESCRIPTION_MAX_LENGTH = 2000;

/**
 * Satın alma talebi form şeması. Tutar burada YALNIZ boş-değil kontrol edilir;
 * TL → kuruş dönüşümü ve sayısal geçerlilik `parseTryToMinor` ile ayrıca yapılır.
 * Nihai doğrulama kaynağı backend'dir.
 */
export const purchaseRequestFormSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, "Başlık gerekli.")
    .max(TITLE_MAX_LENGTH, `Başlık en çok ${TITLE_MAX_LENGTH} karakter olabilir.`),
  description: z
    .string()
    .trim()
    .max(DESCRIPTION_MAX_LENGTH, `Açıklama en çok ${DESCRIPTION_MAX_LENGTH} karakter olabilir.`)
    .optional()
    .default(""),
  amount: z.string().trim().min(1, "Tutar gerekli."),
});

export type PurchaseRequestFormValues = z.infer<typeof purchaseRequestFormSchema>;
