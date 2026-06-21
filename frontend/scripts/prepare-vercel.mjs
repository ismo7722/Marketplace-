import { writeFileSync } from "node:fs"

const DEFAULT_BACKEND = "https://facebook-monitoring-t4py.onrender.com"
const backend = (process.env.BACKEND_URL ?? DEFAULT_BACKEND).trim().replace(/\/$/, "")

/** @type {{ source: string; destination: string }[]} */
const rewrites = [
  { source: "/api/:path*", destination: `${backend}/api/:path*` },
  { source: "/health", destination: `${backend}/health` },
  { source: "/(.*)", destination: "/index.html" },
]

console.log(`[vercel] Proxy /api and /health -> ${backend}`)

writeFileSync("vercel.json", `${JSON.stringify({ rewrites }, null, 2)}\n`)
