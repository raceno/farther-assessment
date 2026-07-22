import { normalizePortfolioResponse } from '../lib/normalizePortfolio'
import type { ClientPortfolio } from '../types/portfolio'

export interface FetchPortfolioResult {
  portfolio: ClientPortfolio
  warnings: string[]
}

function apiBase(): string | undefined {
  const v = import.meta.env.VITE_API_BASE_URL
  return typeof v === 'string' && v.trim() !== '' ? v.replace(/\/$/, '') : undefined
}

export function isApiConfigured(): boolean {
  return Boolean(apiBase())
}

export async function fetchClientPortfolio(clientId: string): Promise<FetchPortfolioResult> {
  const base = apiBase()
  if (!base) {
    throw new Error('VITE_API_BASE_URL is not set')
  }
  const res = await fetch(`${base}/clients/${encodeURIComponent(clientId)}`)
  if (res.status === 404) {
    throw new Error('Client not found')
  }
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`)
  }
  const raw: unknown = await res.json()
  return normalizePortfolioResponse(raw)
}
