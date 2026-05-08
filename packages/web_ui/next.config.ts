import type { NextConfig } from "next";

const cloudApiOrigin = process.env.SOLAMON_CLOUD_ORIGIN ?? "https://cloud.amendi.dev";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${cloudApiOrigin}/api/v1/:path*`
      }
    ];
  }
};

export default nextConfig;
