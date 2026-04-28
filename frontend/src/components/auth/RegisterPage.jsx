import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { registerMerchantUser } from '../../api/client'

const roles = ['USER', 'OPERATOR', 'ADMIN']

function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ merchant_id: '', username: '', email: '', password: '', role: 'USER' })
  const [error, setError] = useState('')

  const onSubmit = async (e) => {
    e.preventDefault()
    const payload = { ...form, merchant_id: Number(form.merchant_id) }
    const { status, data } = await registerMerchantUser(payload)
    if (status !== 201) {
      setError(data?.detail || 'Registration failed')
      return
    }
    navigate('/auth/login', { replace: true })
  }

  return (
    <main className="mx-auto mt-16 max-w-md rounded-xl bg-white p-6 shadow">
      <h1 className="text-xl font-bold">Register</h1>
      <form className="mt-4 space-y-3" onSubmit={onSubmit}>
        <input className="w-full rounded border p-2" placeholder="Merchant ID" value={form.merchant_id} onChange={(e) => setForm((v) => ({ ...v, merchant_id: e.target.value }))} />
        <input className="w-full rounded border p-2" placeholder="Username" value={form.username} onChange={(e) => setForm((v) => ({ ...v, username: e.target.value }))} />
        <input className="w-full rounded border p-2" placeholder="Email" value={form.email} onChange={(e) => setForm((v) => ({ ...v, email: e.target.value }))} />
        <input className="w-full rounded border p-2" placeholder="Password" type="password" value={form.password} onChange={(e) => setForm((v) => ({ ...v, password: e.target.value }))} />
        <select className="w-full rounded border p-2" value={form.role} onChange={(e) => setForm((v) => ({ ...v, role: e.target.value }))}>
          {roles.map((role) => <option key={role} value={role}>{role}</option>)}
        </select>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <button className="w-full rounded bg-slate-900 p-2 text-white" type="submit">Create account</button>
      </form>
      <p className="mt-3 text-sm">Already have an account? <Link className="text-blue-600" to="/auth/login">Login</Link></p>
    </main>
  )
}

export default RegisterPage
