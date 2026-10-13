import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Earlier Cockpit and preview URLs now live at the canonical company routes.
  async redirects() {
    return [
      { source: "/company/:slug/cockpit", destination: "/company/:slug", permanent: false },
      { source: "/company/:slug/cockpit/:questionId", destination: "/company/:slug/question/:questionId", permanent: false },
      { source: "/preview/story/:slug", destination: "/company/:slug", permanent: false },
      { source: "/preview/question/:slug/:questionId", destination: "/company/:slug/question/:questionId", permanent: false },
    ];
  },
};

export default nextConfig;
