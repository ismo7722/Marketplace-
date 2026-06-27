import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date) {
  return new Date(date).toLocaleString("de-CH", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function formatPrice(price: number | null | undefined, currency = "CHF") {
  if (price == null) return "N/A"
  return `${currency} ${price.toLocaleString("de-CH")}`
}

export function formatMileage(mileage: number | null | undefined) {
  if (mileage == null) return "N/A"
  return `${mileage.toLocaleString("de-CH")} km`
}

/** Minimum safe wait between listing checks (account protection). */
export const MIN_SCAN_INTERVAL_SECONDS = 90
export const DEFAULT_SCAN_MIN_SECONDS = 90
export const DEFAULT_SCAN_MAX_SECONDS = 120

/** Five preset blocks — fastest (90–120 s) to slowest (210–240 s). */
export const SCAN_DELAY_PRESETS = [
  { label: "90–120 s", min: 90, max: 120 },
  { label: "120–150 s", min: 120, max: 150 },
  { label: "150–180 s", min: 150, max: 180 },
  { label: "180–210 s", min: 180, max: 210 },
  { label: "210–240 s", min: 210, max: 240 },
]

export function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds} sec`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (s === 0) return `${m} min`
  return `${m} min ${s} sec`
}

/** User-facing check interval, e.g. "90–120 sec (random)" */
export function formatIntervalRange(minSec: number, maxSec: number) {
  if (minSec === maxSec) return `${minSec} sec`
  return `${minSec}–${maxSec} sec (random)`
}
