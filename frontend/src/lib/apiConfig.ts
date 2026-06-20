/** Live Vercel build vs local Vite dev (both use same /api paths; proxy differs). */
export const isLiveDeployment = import.meta.env.PROD

export function getApiBaseUrl(): string {
  return "/api"
}

export function getHealthUrl(): string {
  return "/health"
}
