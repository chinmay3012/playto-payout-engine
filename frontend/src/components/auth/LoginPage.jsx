import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { loginMerchantUser } from '../../api/client'
import { useAuth } from './auth-context'

function LoginPage() {
  const { refreshMe } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const onSubmit = async (e) => {
    e.preventDefault()
    const { status, data } = await loginMerchantUser({ username, password })
    if (status !== 200) {
      setError(data?.detail || 'Login failed')
      return
    }
    await refreshMe()
    navigate(location.state?.from || '/', { replace: true })
  }

  return (
    <main className="mx-auto mt-16 max-w-md rounded-xl bg-white p-6 shadow">
      <h1 className="text-xl font-bold">Login</h1>
      <form className="mt-4 space-y-3" onSubmit={onSubmit}>
        <input className="w-full rounded border p-2" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input className="w-full rounded border p-2" placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <button className="w-full rounded bg-slate-900 p-2 text-white" type="submit">Sign in</button>
      </form>
      <p className="mt-3 text-sm">No account? <Link className="text-blue-600" to="/auth/register">Register</Link></p>
    </main>
  )
}

export default LoginPage
