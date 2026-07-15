import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      // `server-only` marker'ı vitest ortamında no-op'a çözülür; production
      // build'de gerçek paket client-bundle sızmasını engellemeye devam eder.
      "server-only": path.resolve(__dirname, "vitest.server-only-stub.ts"),
    },
  },
  test: {
    environment: "jsdom",
    // Testing Library'nin otomatik cleanup'ı global afterEach'e bağlıdır;
    // globals olmadan DOM testler arasında birikir ve yanlış eşleşme üretir.
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      // Yalnız birim-test edilebilir SAF mantık raporlanır. Dışlananlar:
      // - src/app/**        : sayfa/route bileşenleri (build + smoke ile doğrulanır)
      // - src/proxy.ts      : Next proxy entrypoint (saf kararlar proxy.test.ts'te)
      // - lib/supabase/{client,server}.ts, lib/supabase/proxy.ts(updateSession),
      //   features/*/actions.ts : Supabase SDK + redirect()'e bağlı orkestrasyon;
      //   birim testte tüm SDK mock'lanır (kodu değil mock'u test eder). Build,
      //   typecheck ve (canlı) smoke ile doğrulanır — bkz. README.
      include: [
        // Form testleriyle doğrudan render edilen bileşenler.
        "src/components/alert.tsx",
        "src/components/form-field.tsx",
        "src/components/submit-button.tsx",
        // Saf mantık + form davranışı.
        "src/features/**/schemas.ts",
        "src/features/**/*form*.tsx",
        "src/features/**/action-result.ts",
        "src/lib/api/**",
        "src/lib/redirect.ts",
      ],
      reporter: ["text", "text-summary"],
      thresholds: {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
    },
  },
});
