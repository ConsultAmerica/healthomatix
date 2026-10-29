import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  transpilePackages: ["@healthomatix/api-client"],
};

export default nextConfig;
