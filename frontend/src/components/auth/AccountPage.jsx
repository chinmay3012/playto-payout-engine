import { useState } from 'react'
import { Link } from 'react-router-dom'
import { changePassword, updateAccountProfile } from '../../api/client'
import { useAuth } from './auth-context'

function AccountPage() {
  const { me, refreshMe } = useAuth()
  const [username, setUsername] = useState(me?.username || '')
  const [email, setEmail] = useState(me?.email || '')
  const [message, setMessage] = useState('')
  const [passwordMessage, setPasswordMessage] = useState('')

  const saveProfile = async (e) => {
    e.preventDefault()
    const { status, data } = await updateAccountProfile({ username, email })
    if (status === 200) {
      setMessage('Profile updated')
      await refreshMe()
    } else {
      setMessage(data?.detail || 'Could not update profile')
    }
  }

  const savePassword = async (e) => {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    const payload = {
      current_password: form.get('current_password'),
      new_password: form.get('new_password'),
    }
    const { status, data } = await changePassword(payload)
    setPasswordMessage(status === 200 ? 'Password updated' : data?.detail || 'Could not update password')
    e.currentTarget.reset()
  }

  return (
    <main className="mx-auto mt-8 max-w-2xl space-y-4 rounded-xl bg-white p-6 shadow">
      <div className="flex justify-between">
        <h1 className="text-2xl font-bold">Account</h1>
        <Link className="rounded border px-3 py-2 text-sm" to="/">Dashboard</Link>
      </div>
      <p className="text-sm text-slate-600">Role: {me?.role}</p>
      <form className="space-y-2" onSubmit={saveProfile}>
        <input className="w-full rounded border p-2" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input className="w-full rounded border p-2" value={email} onChange={(e) => setEmail(e.target.value)} />
        <button className="rounded bg-slate-900 px-4 py-2 text-white" type="submit">Save profile</button>
        {message ? <p className="text-sm">{message}</p> : null}
      </form>
      <form className="space-y-2" onSubmit={savePassword}>
        <input className="w-full rounded border p-2" name="current_password" placeholder="Current password" type="password" />
        <input className="w-full rounded border p-2" name="new_password" placeholder="New password" type="password" />
        <button className="rounded bg-slate-900 px-4 py-2 text-white" type="submit">Change password</button>
        {passwordMessage ? <p className="text-sm">{passwordMessage}</p> : null}
      </form>
    </main>
  )
}

export default AccountPage
