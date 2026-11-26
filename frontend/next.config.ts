import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export to out/ for Cloudflare Pages (PRD: no SSR or Server Actions).
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
