/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@xyflow/react"],
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080"}/:path*`,
      },
    ];
  },
};

export default nextConfig;
