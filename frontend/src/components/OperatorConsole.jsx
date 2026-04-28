import { useEffect, useState } from 'react'

import {
  createApiKey,
  createWebhookEndpoint,
  getRiskProfile,
  listApiKeys,
  listWebhookDeliveries,
  listWebhookEndpoints,
  loginMerchantUser,
  registerMerchantUser,
  updateRiskProfile,
} from '../api/client'

function OperatorConsole({ merchantId }) {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('OWNER')
  const [token, setToken] = useState('')
  const [authMessage, setAuthMessage] = useState('')

  const [riskProfile, setRiskProfile] = useState(null)
  const [apiKeys, setApiKeys] = useState([])
  const [webhooks, setWebhooks] = useState([])
  const [deliveries, setDeliveries] = useState([])
  const [newWebhookUrl, setNewWebhookUrl] = useState('')
  const [newApiKeyName, setNewApiKeyName] = useState('Server key')
  const [newApiKeyScopes, setNewApiKeyScopes] = useState('payouts:write')
  const [newlyGeneratedApiKey, setNewlyGeneratedApiKey] = useState('')
  const [opsMessage, setOpsMessage] = useState('')

  const loadOperatorData = async (activeToken) => {
    if (!merchantId) return
    try {
      const [risk, keyList, webhookList, deliveryList] = await Promise.all([
        activeToken ? getRiskProfile(merchantId, activeToken) : Promise.resolve(null),
        listApiKeys(merchantId),
        listWebhookEndpoints(merchantId),
        activeToken ? listWebhookDeliveries(merchantId, activeToken) : Promise.resolve([]),
      ])
      setRiskProfile(risk)
      setApiKeys(keyList)
      setWebhooks(webhookList)
      setDeliveries(deliveryList)
    } catch (e) {
      setOpsMessage('Unable to load operator data')
    }
  }

  useEffect(() => {
    loadOperatorData(token)
  }, [merchantId, token])

  const handleRegister = async (e) => {
    e.preventDefault()
    const { data, status } = await registerMerchantUser({
      merchant_id: merchantId,
      username,
      email,
      password,
      role,
    })
    if (status === 201) setAuthMessage(`User ${data.username} created`)
    else setAuthMessage(data?.detail || 'Register failed')
  }

  const handleLogin = async (e) => {
    e.preventDefault()
    const { data, status } = await loginMerchantUser({ username, password })
    if (status === 200) {
      setToken(data.access_token)
      setAuthMessage(`Logged in as ${data.username} (${data.role})`)
    } else setAuthMessage(data?.detail || 'Login failed')
  }

  const handleRiskUpdate = async (e) => {
    e.preventDefault()
    if (!token || !riskProfile) return
    const { data, status } = await updateRiskProfile(merchantId, riskProfile, token)
    if (status === 200) {
      setRiskProfile(data)
      setOpsMessage('Risk profile updated')
    } else setOpsMessage(data?.detail || 'Risk update failed')
  }

  const handleCreateApiKey = async (e) => {
    e.preventDefault()
    const scopes = newApiKeyScopes
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    const { data, status } = await createApiKey({
      merchant_id: merchantId,
      name: newApiKeyName,
      scopes,
      expires_in_days: 90,
    })
    if (status === 201) {
      setNewlyGeneratedApiKey(data.raw_key)
      setOpsMessage('API key created')
      loadOperatorData(token)
    } else setOpsMessage(data?.detail || 'API key creation failed')
  }

  const handleCreateWebhook = async (e) => {
    e.preventDefault()
    const { data, status } = await createWebhookEndpoint({
      merchant_id: merchantId,
      url: newWebhookUrl,
    })
    if (status === 201) {
      setOpsMessage('Webhook endpoint created')
      setNewWebhookUrl('')
      loadOperatorData(token)
    } else setOpsMessage(data?.detail || 'Webhook creation failed')
  }

  return (
    <section className="rounded-xl bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Operator Console</h2>
      <p className="mt-1 text-xs text-slate-500">
        Auth, API keys, webhooks, risk controls
      </p>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <form className="grid gap-2 rounded-lg border border-slate-200 p-3" onSubmit={handleRegister}>
          <p className="font-medium">Register/Login</p>
          <input className="rounded border px-2 py-1" placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} />
          <input className="rounded border px-2 py-1" placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input className="rounded border px-2 py-1" placeholder="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <select className="rounded border px-2 py-1" value={role} onChange={(e) => setRole(e.target.value)}>
            <option>OWNER</option>
            <option>ADMIN</option>
            <option>OPERATOR</option>
            <option>VIEWER</option>
          </select>
          <div className="flex gap-2">
            <button className="rounded bg-slate-800 px-3 py-1 text-white" type="submit">Register</button>
            <button className="rounded bg-emerald-700 px-3 py-1 text-white" type="button" onClick={handleLogin}>Login</button>
          </div>
          {authMessage ? <p className="text-xs text-slate-600">{authMessage}</p> : null}
        </form>

        <form className="grid gap-2 rounded-lg border border-slate-200 p-3" onSubmit={handleCreateApiKey}>
          <p className="font-medium">API Keys</p>
          <input className="rounded border px-2 py-1" value={newApiKeyName} onChange={(e) => setNewApiKeyName(e.target.value)} />
          <input className="rounded border px-2 py-1" value={newApiKeyScopes} onChange={(e) => setNewApiKeyScopes(e.target.value)} />
          <button className="rounded bg-indigo-700 px-3 py-1 text-white" type="submit">Create key</button>
          {newlyGeneratedApiKey ? <p className="text-xs text-indigo-700 break-all">Raw key: {newlyGeneratedApiKey}</p> : null}
          <p className="text-xs text-slate-500">Active keys: {apiKeys.length}</p>
        </form>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <form className="grid gap-2 rounded-lg border border-slate-200 p-3" onSubmit={handleCreateWebhook}>
          <p className="font-medium">Webhook Endpoints</p>
          <input className="rounded border px-2 py-1" placeholder="https://example.com/webhook" value={newWebhookUrl} onChange={(e) => setNewWebhookUrl(e.target.value)} />
          <button className="rounded bg-amber-700 px-3 py-1 text-white" type="submit">Add endpoint</button>
          <p className="text-xs text-slate-500">Configured: {webhooks.length}</p>
        </form>

        <form className="grid gap-2 rounded-lg border border-slate-200 p-3" onSubmit={handleRiskUpdate}>
          <p className="font-medium">Risk Profile</p>
          <input className="rounded border px-2 py-1" type="number" placeholder="max single payout paise" value={riskProfile?.max_single_payout_paise ?? ''} onChange={(e) => setRiskProfile((p) => ({ ...p, max_single_payout_paise: Number(e.target.value) }))} />
          <input className="rounded border px-2 py-1" type="number" placeholder="daily payout limit paise" value={riskProfile?.daily_payout_limit_paise ?? ''} onChange={(e) => setRiskProfile((p) => ({ ...p, daily_payout_limit_paise: Number(e.target.value) }))} />
          <input className="rounded border px-2 py-1" type="number" placeholder="daily payout count limit" value={riskProfile?.daily_payout_count_limit ?? ''} onChange={(e) => setRiskProfile((p) => ({ ...p, daily_payout_count_limit: Number(e.target.value) }))} />
          <button className="rounded bg-rose-700 px-3 py-1 text-white" type="submit">Update risk profile</button>
        </form>
      </div>

      <div className="mt-4 rounded-lg border border-slate-200 p-3">
        <p className="font-medium">Recent Webhook Delivery Attempts</p>
        <div className="mt-2 max-h-40 overflow-auto text-xs">
          {deliveries.map((d) => (
            <div key={d.id} className="border-b py-1">
              {d.event_type} - {d.endpoint_url} - {d.success ? 'success' : 'failed'} ({d.response_code || 'n/a'})
            </div>
          ))}
          {deliveries.length === 0 ? <p className="text-slate-500">No deliveries yet (login required).</p> : null}
        </div>
      </div>

      {opsMessage ? <p className="mt-2 text-xs text-slate-600">{opsMessage}</p> : null}
    </section>
  )
}

export default OperatorConsole
