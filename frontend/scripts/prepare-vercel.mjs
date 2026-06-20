import { writeFileSync } from "node:fs"

const backend = (process.env.BACKEND_URL ?? "").trim().replace(/\/$/, "")

/** @type {{ source: string; destination: string }[]} */
const rewrites = []

if (backend) {
  rewrites.push(
    { source: "/api/:path*", destination: `${backend}/api/:path*` },
    { source: "/health", destination: `${backend}/health` },
  )
  console.log(`[vercel] Proxy /api and /health -> ${backend}`)
} else {
  console.warn("[vercel] BACKEND_URL not set — dashboard UI only until you add your tunnel URL on Vercel")
}

rewrites.push({ source: "/(.*)", destination: "/index.html" })

writeFileSync("vercel.json", `${JSON.stringify({ rewrites }, null, 2)}\n`)
