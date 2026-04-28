import { useMemo, useState } from 'react'

import { createPayout } from '../api/client'
import { inrToPaise } from '../utils'

function PayoutForm({ merchantId, bankAccounts = [], onSuccess }) {
  const [amountInr, setAmountInr] = useState('')
  const [bankAccountId, setBankAccountId] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const hasAccounts = useMemo(() => bankAccounts.length > 0, [bankAccounts])

  const submitPayout = async (e) => {
    e.preventDefault()
    if (!merchantId) return

    const amountPaise = inrToPaise(amountInr)
    if (amountPaise <= 0) {
      setError('Enter a valid positive payout amount')
      return
    }

    if (!bankAccountId) {
      setError('Please select a bank account')
      return
    }

    setIsSubmitting(true)
    setError('')

    try {
      const idempotencyKey = crypto.randomUUID()
      const { data, status } = await createPayout({
        merchantId,
        amountPaise,
        bankAccountId: Number(bankAccountId),
        idempotencyKey,
      })

      if (status === 201) {
        setAmountInr('')
        onSuccess?.()
        return
      }

      if (status === 200) {
        onSuccess?.()
        return
      }

      setError(data?.detail || 'Payout request failed')
    } catch {
      setError('Unexpected error while creating payout')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-lg">
      <h2 className="text-lg font-semibold text-white">Request Payout</h2>
      <p className="mt-1 text-xs text-slate-400">Creates a PENDING payout with idempotency protection.</p>
      <form className="mt-4 grid gap-3" onSubmit={submitPayout}>
        <label className="text-sm font-medium text-slate-300" htmlFor="payout-amount">
          Amount (INR)
        </label>
        <input
          id="payout-amount"
          type="number"
          min="0"
          step="0.01"
          value={amountInr}
          onChange={(e) => setAmountInr(e.target.value)}
          className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-emerald-500/60 focus:ring"
          placeholder="e.g. 1000"
        />

        <label className="text-sm font-medium text-slate-300" htmlFor="bank-account">
          Bank account
        </label>
        <select
          id="bank-account"
          value={bankAccountId}
          onChange={(e) => setBankAccountId(e.target.value)}
          className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none ring-emerald-500/60 focus:ring disabled:opacity-70"
          disabled={!hasAccounts}
        >
          <option value="">{hasAccounts ? 'Select account' : 'No active bank accounts found'}</option>
          {bankAccounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.ifsc} - ****{account.account_number.slice(-4)}
            </option>
          ))}
        </select>
        <p className="text-xs text-slate-500">Loaded accounts: {bankAccounts.length}</p>

        {error ? (
          <p className="rounded-md border border-red-500/30 bg-red-950/40 px-3 py-2 text-sm text-red-200">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={isSubmitting || !hasAccounts}
          className="mt-2 rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? 'Submitting...' : 'Request payout'}
        </button>
      </form>
    </section>
  )
}

export default PayoutForm
