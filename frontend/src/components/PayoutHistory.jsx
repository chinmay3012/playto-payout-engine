import { useEffect, useState } from 'react'

import { getMerchantPayouts } from '../api/client'
import { paiseToInr } from '../utils'

const statusClassMap = {
  PENDING: 'bg-slate-800 text-slate-200 border border-slate-600',
  PROCESSING: 'bg-amber-500/10 text-amber-200 border border-amber-500/30',
  COMPLETED: 'bg-emerald-500/10 text-emerald-200 border border-emerald-500/30',
  FAILED: 'bg-red-500/10 text-red-200 border border-red-500/30',
}

function PayoutHistory({ merchantId, refreshTick }) {
  const [payouts, setPayouts] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    if (!merchantId) return undefined

    let cancelled = false

    const fetchPayouts = async () => {
      try {
        const data = await getMerchantPayouts(merchantId)
        if (!cancelled) {
          setPayouts(data.results || [])
          setError('')
        }
      } catch {
        if (!cancelled) {
          setError('Unable to fetch payouts')
        }
      }
    }

    fetchPayouts()
    const interval = setInterval(fetchPayouts, 5000)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [merchantId, refreshTick])

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-lg">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Payout History</h2>
        <span className="text-xs text-slate-400">Live status polling every 5s</span>
      </div>
      {error ? (
        <p className="mt-2 rounded-md border border-red-500/30 bg-red-950/40 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      ) : null}
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-slate-400">
            <tr>
              <th className="pb-2">ID</th>
              <th className="pb-2">Amount</th>
              <th className="pb-2">Status</th>
              <th className="pb-2">Created</th>
            </tr>
          </thead>
          <tbody>
            {payouts.map((payout) => (
              <tr key={payout.id} className="border-t border-slate-800">
                <td className="py-2 text-slate-200">#{payout.id}</td>
                <td className="py-2 text-slate-100">₹{paiseToInr(payout.amount_paise)}</td>
                <td className="py-2">
                  <span
                    className={`rounded-full px-2 py-1 text-xs font-semibold ${statusClassMap[payout.status] || 'bg-slate-800 text-slate-200 border border-slate-700'}`}
                  >
                    {payout.status}
                  </span>
                </td>
                <td className="py-2 text-slate-400">{new Date(payout.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {payouts.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-6 text-center text-sm text-slate-500">
                  No payouts yet. Submit one request to see live status transitions.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default PayoutHistory
