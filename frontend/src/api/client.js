import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const getMerchants = async () => {
  const { data } = await api.get('/api/v1/merchants/')
  return data
}

export const getMerchantBalance = async (merchantId) => {
  const { data } = await api.get(`/api/v1/merchants/${merchantId}/balance/`)
  return data
}

export const getMerchantLedger = async (merchantId) => {
  const { data } = await api.get(`/api/v1/merchants/${merchantId}/ledger/`)
  return data
}

export const getMerchantBankAccounts = async (merchantId) => {
  const { data } = await api.get(`/api/v1/merchants/${merchantId}/bank-accounts/`)
  return data
}

export const getMerchantPayouts = async (merchantId) => {
  const { data } = await api.get(`/api/v1/merchants/${merchantId}/payouts/`)
  return data
}

export const createPayout = async ({ merchantId, amountPaise, bankAccountId, idempotencyKey }) => {
  const { data, status } = await api.post(
    '/api/v1/payouts/',
    {
      merchant_id: merchantId,
      amount_paise: amountPaise,
      bank_account_id: bankAccountId,
    },
    {
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
      validateStatus: (s) => s >= 200 && s < 500,
    }
  )

  return { data, status }
}

export const registerMerchantUser = async (payload) => {
  const { data, status } = await api.post('/api/v1/auth/register/', payload, {
    validateStatus: (s) => s >= 200 && s < 500,
  })
  return { data, status }
}

export const loginMerchantUser = async (payload) => {
  const { data, status } = await api.post('/api/v1/auth/login/', payload, {
    validateStatus: (s) => s >= 200 && s < 500,
  })
  return { data, status }
}

export const refreshSession = async () => {
  const { data, status } = await api.post('/api/v1/auth/refresh/', {}, {
    validateStatus: (s) => s >= 200 && s < 500,
  })
  return { data, status }
}

export const logoutMerchantUser = async () => {
  const { data, status } = await api.post('/api/v1/auth/logout/', {}, {
    validateStatus: (s) => s >= 200 && s < 500,
  })
  return { data, status }
}

export const getMe = async () => {
  const { data, status } = await api.get('/api/v1/auth/me/', {
    validateStatus: (s) => s >= 200 && s < 500,
  })
  return { data, status }
}

export const getRiskProfile = async (merchantId, token) => {
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined
  const { data } = await api.get(`/api/v1/merchants/${merchantId}/risk-profile/`, { headers })
  return data
}

export const updateRiskProfile = async (merchantId, payload, token) => {
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined
  const { data, status } = await api.patch(`/api/v1/merchants/${merchantId}/risk-profile/`, payload, {
    headers,
    validateStatus: (s) => s >= 200 && s < 500,
  })
  return { data, status }
}

export const updateAccountProfile = async (payload) => {
  const { data, status } = await api.patch('/api/v1/account/profile/', payload, {
    validateStatus: (s) => s >= 200 && s < 500,
  })
  return { data, status }
}

export const changePassword = async (payload) => {
  const { data, status } = await api.post('/api/v1/account/change-password/', payload, {
    validateStatus: (s) => s >= 200 && s < 500,
  })
  return { data, status }
}

export const listApiKeys = async (merchantId) => {
  const { data } = await api.get('/api/v1/api-keys/', { params: { merchant_id: merchantId } })
  return data
}

export const createApiKey = async (payload) => {
  const { data, status } = await api.post('/api/v1/api-keys/', payload, {
    validateStatus: (s) => s >= 200 && s < 500,
  })
  return { data, status }
}

export const listWebhookEndpoints = async (merchantId) => {
  const { data } = await api.get('/api/v1/webhook-endpoints/', {
    params: { merchant_id: merchantId },
  })
  return data
}

export const createWebhookEndpoint = async (payload) => {
  const { data, status } = await api.post('/api/v1/webhook-endpoints/', payload, {
    validateStatus: (s) => s >= 200 && s < 500,
  })
  return { data, status }
}

export const listWebhookDeliveries = async (merchantId, token) => {
  const { data } = await api.get(`/api/v1/merchants/${merchantId}/webhook-deliveries/`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return data
}

export default api
