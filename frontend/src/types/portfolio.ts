/** Vocabulary aligned with backend / partner payloads */

export type AccountType =
  | 'INDIVIDUAL'
  | 'ROTH_IRA'
  | 'TRAD_IRA'
  | 'JOINT'
  | (string & {})

export type AccountStatus = 'ACTIVE' | 'INACTIVE' | 'CLOSED' | (string & {})

export type AssetClass =
  | 'US_EQUITY'
  | 'INTL_EQUITY'
  | 'FIXED_INCOME'
  | 'CASH'
  | 'ALTERNATIVE'
  | (string & {})

export interface Holding {
  ticker: string | null
  cusip: string | null
  description: string | null
  quantity: number | null
  market_value: number | null
  cost_basis: number | null
  price: number | null
  asset_class: AssetClass | null
}

export interface Account {
  account_id: string
  account_type: AccountType
  custodian: string | null
  opened_date: string | null
  status: AccountStatus
  holdings: Holding[]
  cash_balance: number | null
  total_value: number | null
}

export interface ClientPortfolio {
  client_id: string
  first_name: string
  last_name: string
  email: string
  accounts: Account[]
  advisor_id: string | null
  last_updated: string | null
}
