import type { NextConfig } from "next";

// The browser only ever talks to this Next.js server. API calls are proxied to FastAPI, so there is
// no CORS, and the httpOnly refresh cookie (path /auth, SameSite=strict) is same-origin.
const API_URL = process.env.API_URL ?? "http://localhost:8001";

const nextConfig: NextConfig = {
  // No Cache Components: every screen is a client view of live data behind a login (nothing to prerender
  // or cache server-side), and the Redux store must be created in the browser.
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL}/:path*` },
      { source: "/auth/:path*", destination: `${API_URL}/auth/:path*` },
    ];
  },
};

export default nextConfig;
