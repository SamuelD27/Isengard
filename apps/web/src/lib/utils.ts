import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function generateCorrelationId(): string {
  return `fe-${Date.now().toString(36)}-${Math.random().toString(36).substr(2, 9)}`
}
