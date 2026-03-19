import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@local-figma/shared-types", "@local-figma/preview-bridge"],
};

export default nextConfig;
