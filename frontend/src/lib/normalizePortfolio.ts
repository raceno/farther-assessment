import type { Account, ClientPortfolio, Holding } from '../types/portfolio'

export interface NormalizeResult {
  portfolio: ClientPortfolio
  warnings: string[]
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function asString(v: unknown, path: string, warnings: string[]): string {
  if (v === undefined || v === null) {
    warnings.push(`${path}: missing, using empty string`)
    return ''
  }
  if (typeof v === 'string') return v
  warnings.push(`${path}: expected string, got ${typeof v}`)
  return String(v)
}

function asStringOrNull(v: unknown): string | null {
  if (v === undefined || v === null) return null
  if (typeof v === 'string') return v
  return String(v)
}

function asNumberOrNull(v: unknown, path: string, warnings: string[]): number | null {
  if (v === undefined || v === null) return null
  if (typeof v === 'number' && !Number.isNaN(v)) return v
  if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) {
    return Number(v)
  }
  warnings.push(`${path}: expected number, using null`)
  return null
}

function normalizeHolding(raw: unknown, idx: number, warnings: string[]): Holding {
  const base = `accounts[].holdings[${idx}]`
  if (!isRecord(raw)) {
    warnings.push(`${base}: not an object, skipped fields`)
    return {
      ticker: null,
      cusip: null,
      description: null,
      quantity: null,
      market_value: null,
      cost_basis: null,
      price: null,
      asset_class: null,
    }
  }
  return {
    ticker: asStringOrNull(raw.ticker),
    cusip: asStringOrNull(raw.cusip),
    description: asStringOrNull(raw.description),
    quantity: asNumberOrNull(raw.quantity, `${base}.quantity`, warnings),
    market_value: asNumberOrNull(raw.market_value, `${base}.market_value`, warnings),
    cost_basis: asNumberOrNull(raw.cost_basis, `${base}.cost_basis`, warnings),
    price: asNumberOrNull(raw.price, `${base}.price`, warnings),
    asset_class: asStringOrNull(raw.asset_class) as Holding['asset_class'],
  }
}

function normalizeAccount(raw: unknown, idx: number, warnings: string[]): Account {
  const base = `accounts[${idx}]`
  if (!isRecord(raw)) {
    warnings.push(`${base}: not an object`)
    return {
      account_id: `unknown-${idx}`,
      account_type: 'UNKNOWN',
      custodian: null,
      opened_date: null,
      status: 'UNKNOWN',
      holdings: [],
      cash_balance: null,
      total_value: null,
    }
  }
  const holdingsRaw = raw.holdings
  const holdings: Holding[] = Array.isArray(holdingsRaw)
    ? holdingsRaw.map((h, i) => normalizeHolding(h, i, warnings))
    : (warnings.push(`${base}.holdings: expected array, using []`), [])

  return {
    account_id: asString(raw.account_id, `${base}.account_id`, warnings),
    account_type: asString(raw.account_type, `${base}.account_type`, warnings),
    custodian: asStringOrNull(raw.custodian),
    opened_date: asStringOrNull(raw.opened_date),
    status: asString(raw.status, `${base}.status`, warnings),
    holdings,
    cash_balance: asNumberOrNull(raw.cash_balance, `${base}.cash_balance`, warnings),
    total_value: asNumberOrNull(raw.total_value, `${base}.total_value`, warnings),
  }
}

/**
 * Coerces an unknown API/document payload into {@link ClientPortfolio}.
 * Logs soft issues as `warnings` instead of throwing — useful when the partner
 * adds fields or sends occasional type drift.
 */
export function normalizePortfolioResponse(raw: unknown): NormalizeResult {
  const warnings: string[] = []
  if (!isRecord(raw)) {
    warnings.push('root: expected object, returning empty portfolio')
    return {
      portfolio: {
        client_id: '',
        first_name: '',
        last_name: '',
        email: '',
        accounts: [],
        advisor_id: null,
        last_updated: null,
      },
      warnings,
    }
  }

  const accountsRaw = raw.accounts
  const accounts: Account[] = Array.isArray(accountsRaw)
    ? accountsRaw.map((a, i) => normalizeAccount(a, i, warnings))
    : (warnings.push('accounts: expected array, using []'), [])

  const portfolio: ClientPortfolio = {
    client_id: asString(raw.client_id, 'client_id', warnings),
    first_name: asString(raw.first_name, 'first_name', warnings),
    last_name: asString(raw.last_name, 'last_name', warnings),
    email: asString(raw.email, 'email', warnings),
    accounts,
    advisor_id: asStringOrNull(raw.advisor_id),
    last_updated: asStringOrNull(raw.last_updated),
  }

  return { portfolio, warnings }
}
