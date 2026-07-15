/**
 * Auth form şemaları — saf Zod, server action'lar ve client ön-doğrulama
 * tarafından paylaşılır. Nihai doğrulama HER ZAMAN server tarafındadır.
 */

import { z } from "zod";

export const MIN_PASSWORD_LENGTH = 8;

export const signInSchema = z.object({
  email: z.email("Geçerli bir e-posta adresi girin."),
  password: z.string().min(1, "Şifre gerekli."),
});

export const signUpSchema = z
  .object({
    email: z.email("Geçerli bir e-posta adresi girin."),
    password: z
      .string()
      .min(MIN_PASSWORD_LENGTH, `Şifre en az ${MIN_PASSWORD_LENGTH} karakter olmalı.`),
    passwordConfirm: z.string(),
  })
  .refine((data) => data.password === data.passwordConfirm, {
    message: "Şifreler eşleşmiyor.",
    path: ["passwordConfirm"],
  });

export type SignInInput = z.infer<typeof signInSchema>;
export type SignUpInput = z.infer<typeof signUpSchema>;
