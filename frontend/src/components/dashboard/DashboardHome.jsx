import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getMerchantBankAccounts, getMerchants } from '../../api/client'
import BalanceCard from '../BalanceCard'
import LedgerTable from '../LedgerTable'
import PayoutForm from '../PayoutForm'
import PayoutHistory from '../PayoutHistory'
import { useAuth } from '../auth/auth-context'

function DashboardHome() {
  const { me, logout } = useAuth()
  const [merchants, setMerchants] = useState([])
  const [selectedMerchantId, setSelectedMerchantId] = useState('')
  const [bankAccounts, setBankAccounts] = useState([])
  const [refreshTick, setRefreshTick] = useState(0)
  const [error, setError] = useState('')
  const [isLoadingMerchants, setIsLoadingMerchants] = useState(true)

  useEffect(() => {
    let cancelled = false
    const fetchMerchants = async () => {
      setIsLoadingMerchants(true)
      try {
        const data = await getMerchants()
        if (!cancelled) {
          setMerchants(data)
          setError('')
          if (me?.merchant_id) {
            setSelectedMerchantId(String(me.merchant_id))
          } else if (data.length > 0) {
            setSelectedMerchantId(String(data[0].id))
          }
        }
      } catch {
        if (!cancelled) setError('Unable to load merchants. Ensure backend is running.')
      } finally {
        if (!cancelled) setIsLoadingMerchants(false)
      }
    }
    fetchMerchants()
    return () => {
      cancelled = true
    }
  }, [me?.merchant_id])

  useEffect(() => {
    if (!selectedMerchantId) return undefined
    let cancelled = false
    const fetchBankAccounts = async () => {
      try {
        const data = await getMerchantBankAccounts(selectedMerchantId)
        if (!cancelled) setBankAccounts(data)
      } catch {
        if (!cancelled) setBankAccounts([])
      }
    }
    fetchBankAccounts()
    return () => {
      cancelled = true
    }
  }, [selectedMerchantId])

  const selectedMerchant = useMemo(
    () => merchants.find((m) => String(m.id) === selectedMerchantId),
    [merchants, selectedMerchantId]
  )

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-950/40 shadow-xl">
          <div className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-emerald-300/90">
                Playto Payout Engine
              </p>
              <h1 className="mt-1 text-2xl font-bold text-white">Merchant Payout Dashboard</h1>
              <p className="mt-1 text-sm text-slate-300">
                Signed in as {me?.username} ({me?.role})
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-emerald-400 hover:text-emerald-300"
                to="/account"
              >
                Account
              </Link>
              {me?.role === 'ADMIN' || me?.role === 'OWNER' ? (
                <Link
                  className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-emerald-400 hover:text-emerald-300"
                  to="/admin/home"
                >
                  Admin
                </Link>
              ) : null}
              {['OPERATOR', 'ADMIN', 'OWNER'].includes(me?.role || '') ? (
                <Link
                  className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-emerald-400 hover:text-emerald-300"
                  to="/operator/home"
                >
                  Operator
                </Link>
              ) : null}
              <button
                className="rounded-md bg-emerald-500 px-3 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400"
                onClick={logout}
              >
                Logout
              </button>
            </div>
          </div>
        </header>
        {error ? (
          <p className="rounded-lg border border-red-500/30 bg-red-950/40 px-4 py-3 text-sm text-red-200">
            {error}
          </p>
        ) : null}
        <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-4 shadow-lg">
          <div>
            <p className="text-sm font-medium text-slate-300">Merchant Context</p>
            <p className="text-xs text-slate-500">
              Select merchant account to view balance, payouts, and ledger activity.
            </p>
          </div>
          <div className="mt-3 min-w-60">
            <label className="mb-1 block text-sm font-medium text-slate-300" htmlFor="merchant-select">
              Merchant
            </label>
            <select
              id="merchant-select"
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-emerald-500/60 transition focus:ring"
              value={selectedMerchantId}
              onChange={(e) => setSelectedMerchantId(e.target.value)}
              disabled={isLoadingMerchants}
            >
              <option value="">{isLoadingMerchants ? 'Loading merchants...' : 'Select merchant'}</option>
              {merchants.map((merchant) => (
                <option key={merchant.id} value={merchant.id}>
                  {merchant.name}
                </option>
              ))}
            </select>
          </div>
        </section>
        {selectedMerchant ? (
          <>
            <BalanceCard merchantId={selectedMerchant.id} refreshTick={refreshTick} />
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <PayoutForm
                merchantId={selectedMerchant.id}
                bankAccounts={bankAccounts}
                onSuccess={() => setRefreshTick((v) => v + 1)}
              />
              <PayoutHistory merchantId={selectedMerchant.id} refreshTick={refreshTick} />
            </div>
            <LedgerTable merchantId={selectedMerchant.id} refreshTick={refreshTick} />
          </>
        ) : null}
      </div>
    </main>
  )
}

export default DashboardHome
