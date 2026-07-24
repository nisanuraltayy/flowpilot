import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Container packaging (FP-OPS-001): standalone output, uygulamanın çalışması için
  // gereken minimum dosya kümesini `.next/standalone` altına üretir; production
  // image'ında dev/build bağımlılıkları taşınmaz.
  //
  // NOT: Güvenlik header'ları (CSP/HSTS/X-Frame-Options ...) bilinçli olarak BURADA
  // YOKTUR — FP-OPS-003 kapsamındadır.
  output: "standalone",
};

export default nextConfig;
