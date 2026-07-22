import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchClientPortfolio, isApiConfigured } from '../api/fetchClientPortfolio'
import sampleRaw from '../data/sample-portfolio.json'
import { formatPct, formatQty, formatUsd } from '../lib/format'
import { normalizePortfolioResponse } from '../lib/normalizePortfolio'
import type { Account, ClientPortfolio, Holding } from '../types/portfolio'

export default function PortfolioPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const clientIdFromUrl = searchParams.get('clientId') ?? 'CLT-29481'
  const accountFromUrl = searchParams.get('account')

  const [portfolio, setPortfolio] = useState<ClientPortfolio | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [loadState, setLoadState] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [useApi, setUseApi] = useState(() => isApiConfigured())

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoadState('loading')
      setErrorMessage(null)
      try {
        let normalized
        if (useApi && isApiConfigured()) {
          normalized = await fetchClientPortfolio(clientIdFromUrl.trim())
        } else {
          normalized = normalizePortfolioResponse(sampleRaw)
        }
        if (cancelled) return
        setPortfolio(normalized.portfolio)
        setWarnings(normalized.warnings)
        setLoadState('ok')
      } catch (err) {
        if (cancelled) return
        setPortfolio(null)
        setWarnings([])
        setErrorMessage(err instanceof Error ? err.message : 'Something went wrong')
        setLoadState('error')
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [clientIdFromUrl, useApi])

  const selectedAccountId = useMemo(() => {
    if (!portfolio?.accounts.length) return null
    const ids = new Set(portfolio.accounts.map((a) => a.account_id))
    if (accountFromUrl && ids.has(accountFromUrl)) return accountFromUrl
    return portfolio.accounts[0].account_id
  }, [portfolio, accountFromUrl])

  const selectedAccount: Account | null = useMemo(() => {
    if (!portfolio || !selectedAccountId) return null
    return portfolio.accounts.find((a) => a.account_id === selectedAccountId) ?? null
  }, [portfolio, selectedAccountId])

  const holdingsTotalMv = useMemo(() => {
    if (!selectedAccount) return 0
    return selectedAccount.holdings.reduce((sum, h) => sum + (h.market_value ?? 0), 0)
  }, [selectedAccount])

  function applyClientIdToUrl(nextId: string) {
    setSearchParams((prev) => {
      const n = new URLSearchParams(prev)
      n.set('clientId', nextId)
      n.delete('account')
      return n
    })
  }

  function selectAccount(accountId: string) {
    setSearchParams((prev) => {
      const n = new URLSearchParams(prev)
      n.set('clientId', clientIdFromUrl)
      n.set('account', accountId)
      return n
    })
  }

  function onSubmitLookup(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const raw = String(fd.get('clientId') ?? '').trim()
    applyClientIdToUrl(raw || 'CLT-29481')
  }

  const apiAvailable = isApiConfigured()

  return (
    <div className="page">
      <header className="page-header">
        <h1>Portfolio breakdown</h1>
        <p className="lede">
          Inspect nested accounts and holdings. Account selection syncs to the URL for deep links.
        </p>
      </header>

      <section className="panel controls">
        <form className="lookup-form" onSubmit={onSubmitLookup}>
          <label className="field">
            <span>Client ID</span>
            <input
              key={clientIdFromUrl}
              name="clientId"
              defaultValue={clientIdFromUrl}
              placeholder="CLT-29481"
              autoComplete="off"
            />
          </label>
          <button type="submit" disabled={loadState === 'loading'}>
            Load
          </button>
        </form>

        <label className="toggle">
          <input
            type="checkbox"
            checked={useApi}
            disabled={!apiAvailable}
            onChange={(e) => setUseApi(e.target.checked)}
          />
          <span>
            Fetch from API {apiAvailable ? `(base: ${import.meta.env.VITE_API_BASE_URL})` : '(set VITE_API_BASE_URL)'}
          </span>
        </label>
      </section>

      {loadState === 'loading' && <p className="banner muted">Loading…</p>}
      {loadState === 'error' && errorMessage && (
        <div className="banner error" role="alert">
          {errorMessage}
          {!useApi && (
            <span className="hint"> Demo JSON still works offline — enable API after ingest.</span>
          )}
        </div>
      )}

      {warnings.length > 0 && loadState === 'ok' && (
        <details className="banner warn">
          <summary>{warnings.length} normalization warning(s)</summary>
          <ul>
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </details>
      )}

      {loadState === 'ok' && portfolio && (
        <>
          <section className="panel summary">
            <div>
              <h2 className="summary-name">
                {portfolio.first_name} {portfolio.last_name}
              </h2>
              <p className="meta">
                <span>{portfolio.email}</span>
                <span className="sep">·</span>
                <span>Client {portfolio.client_id}</span>
                {portfolio.advisor_id && (
                  <>
                    <span className="sep">·</span>
                    <span>Advisor {portfolio.advisor_id}</span>
                  </>
                )}
              </p>
            </div>
            <div className="summary-aside">
              {portfolio.last_updated && (
                <p className="meta">
                  Last updated{' '}
                  <time dateTime={portfolio.last_updated}>{portfolio.last_updated}</time>
                </p>
              )}
              <p className="meta">
                {portfolio.accounts.length} account{portfolio.accounts.length === 1 ? '' : 's'}
              </p>
            </div>
          </section>

          {!portfolio.accounts.length && (
            <div className="panel empty">
              <p>This client has no brokerage accounts to display.</p>
            </div>
          )}

          {portfolio.accounts.length > 0 && (
            <>
              <nav className="account-tabs" aria-label="Accounts">
                {portfolio.accounts.map((acc) => {
                  const active = acc.account_id === selectedAccountId
                  return (
                    <button
                      key={acc.account_id}
                      type="button"
                      className={active ? 'tab active' : 'tab'}
                      onClick={() => selectAccount(acc.account_id)}
                    >
                      <span className="tab-id">{acc.account_id}</span>
                      <span className="tab-type">{acc.account_type}</span>
                    </button>
                  )
                })}
              </nav>

              {selectedAccount && (
                <section className="panel holdings-wrap">
                  <div className="holdings-head">
                    <div>
                      <h3>Holdings</h3>
                      <p className="meta">
                        {selectedAccount.custodian && <span>{selectedAccount.custodian}</span>}
                        {selectedAccount.opened_date && (
                          <>
                            <span className="sep">·</span>
                            <span>Opened {selectedAccount.opened_date}</span>
                          </>
                        )}
                        <span className="sep">·</span>
                        <span>{selectedAccount.status}</span>
                      </p>
                    </div>
                    <div className="totals">
                      <div>
                        <span className="totals-label">Account total</span>
                        <span className="totals-value">{formatUsd(selectedAccount.total_value)}</span>
                      </div>
                      <div>
                        <span className="totals-label">Cash</span>
                        <span className="totals-value">{formatUsd(selectedAccount.cash_balance)}</span>
                      </div>
                    </div>
                  </div>

                  <HoldingsTable
                    holdings={selectedAccount.holdings}
                    holdingsTotalMv={holdingsTotalMv}
                    accountTotal={selectedAccount.total_value}
                  />
                </section>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}

function HoldingsTable({
  holdings,
  holdingsTotalMv,
  accountTotal,
}: {
  holdings: Holding[]
  holdingsTotalMv: number
  accountTotal: number | null
}) {
  const cashSlice =
    accountTotal != null && !Number.isNaN(accountTotal)
      ? Math.max(0, accountTotal - holdingsTotalMv)
      : null

  return (
    <div className="table-scroll">
      <table className="holdings-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Description</th>
            <th className="num">Qty</th>
            <th className="num">Price</th>
            <th className="num">Market value</th>
            <th className="num">Cost basis</th>
            <th>Asset class</th>
            <th className="num">% of account</th>
          </tr>
        </thead>
        <tbody>
          {holdings.length === 0 && (
            <tr>
              <td colSpan={8} className="empty-cell">
                No holdings in this account.
              </td>
            </tr>
          )}
          {holdings.map((h) => (
            <tr key={`${h.cusip ?? ''}-${h.ticker ?? ''}-${h.description ?? ''}`}>
              <td className="mono">{h.ticker ?? '—'}</td>
              <td>{h.description ?? '—'}</td>
              <td className="num">{formatQty(h.quantity)}</td>
              <td className="num">{formatUsd(h.price)}</td>
              <td className="num">{formatUsd(h.market_value)}</td>
              <td className="num">{formatUsd(h.cost_basis)}</td>
              <td>
                <span className="pill">{h.asset_class ?? '—'}</span>
              </td>
              <td className="num">
                {accountTotal != null && accountTotal > 0 && h.market_value != null
                  ? formatPct(h.market_value, accountTotal)
                  : '—'}
              </td>
            </tr>
          ))}
          {cashSlice != null && cashSlice > 0.005 && (
            <tr className="cash-row">
              <td className="mono">CASH</td>
              <td>Cash &amp; equivalents</td>
              <td className="num">—</td>
              <td className="num">—</td>
              <td className="num">{formatUsd(cashSlice)}</td>
              <td className="num">—</td>
              <td>
                <span className="pill">CASH</span>
              </td>
              <td className="num">
                {accountTotal != null && accountTotal > 0
                  ? formatPct(cashSlice, accountTotal)
                  : '—'}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
