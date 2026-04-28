import { useEffect, useState } from 'react'

import { getMerchantLedger } from '../api/client'
import { paiseToInr } from '../utils'

function LedgerTable({ merchantId, refreshTick }) {
  const [entries, setEntries] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    if (!merchantId) return undefined

    let cancelled = false

    const fetchLedger = async () => {
      try {
        const data = await getMerchantLedger(merchantId)
        if (!cancelled) {
          setEntries(data.results || [])
          setError('')
        }
      } catch {
        if (!cancelled) {
          setError('Unable to fetch ledger entries')
        }
      }
    }

    fetchLedger()

    return () => {
      cancelled = true
    }
  }, [merchantId, refreshTick])

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-lg">
      <h2 className="text-lg font-semibold text-white">Recent Ledger</h2>
      <p className="mt-1 text-xs text-slate-400">Append-only money movement trail (credits and debits).</p>
      {error ? (
        <p className="mt-2 rounded-md border border-red-500/30 bg-red-950/40 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      ) : null}
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-slate-400">
            <tr>
              <th className="pb-2">Type</th>
              <th className="pb-2">Amount</th>
              <th className="pb-2">Description</th>
              <th className="pb-2">Date</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} className="border-t border-slate-800">
                <td
                  className={`py-2 font-medium ${entry.entry_type === 'CREDIT' ? 'text-emerald-300' : 'text-red-300'}`}
                >
                  {entry.entry_type === 'CREDIT' ? 'Credit' : 'Debit'}
                </td>
                <td className="py-2 text-slate-100">₹{paiseToInr(entry.amount_paise)}</td>
                <td className="py-2 text-slate-300">{entry.description}</td>
                <td className="py-2 text-slate-400">{new Date(entry.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {entries.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-6 text-center text-sm text-slate-500">
                  No ledger entries found for this merchant.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default LedgerTable
