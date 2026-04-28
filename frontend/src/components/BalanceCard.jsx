import { useEffect, useState } from 'react'

import { getMerchantBalance } from '../api/client'
import { paiseToInr } from '../utils'

function BalanceCard({ merchantId, refreshTick }) {
  const [balance, setBalance] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!merchantId) return undefined

    let cancelled = false

    const fetchBalance = async () => {
      try {
        const data = await getMerchantBalance(merchantId)
        if (!cancelled) {
          setBalance(data)
          setError('')
        }
      } catch (e) {
        if (!cancelled) {
          setError('Unable to fetch balance')
        }
      }
    }

    fetchBalance()
    const interval = setInterval(fetchBalance, 5000)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [merchantId, refreshTick])

  if (!merchantId) return null

  const computedTotalInr = paiseToInr(
    Number(balance?.available_paise || 0) + Number(balance?.held_paise || 0)
  )

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-lg">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Balance Overview</h2>
        <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-300">
          Auto-refresh: 5s
        </span>
      </div>
      {error ? (
        <p className="mt-2 rounded-md border border-red-500/30 bg-red-950/40 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      ) : null}
      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4">
          <p className="text-xs uppercase tracking-wide text-emerald-300">Available</p>
          <p className="mt-1 text-2xl font-semibold text-emerald-100">₹{balance?.available_inr || '0.00'}</p>
        </div>
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-4">
          <p className="text-xs uppercase tracking-wide text-amber-300">Held (In flight)</p>
          <p className="mt-1 text-2xl font-semibold text-amber-100">₹{balance?.held_inr || '0.00'}</p>
        </div>
        <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/10 p-4">
          <p className="text-xs uppercase tracking-wide text-indigo-300">Total (Available + Held)</p>
          <p className="mt-1 text-2xl font-semibold text-indigo-100">₹{computedTotalInr}</p>
        </div>
      </div>
    </section>
  )
}

export default BalanceCard
