import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { getMe, logoutMerchantUser } from '../../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [me, setMe] = useState(null)
  const [isBootstrapping, setIsBootstrapping] = useState(true)

  const refreshMe = async () => {
    const { data, status } = await getMe()
    if (status === 200) {
      setMe(data)
      return data
    }
    setMe(null)
    return null
  }

  const logout = async () => {
    await logoutMerchantUser()
    setMe(null)
  }

  useEffect(() => {
    let cancelled = false
    const bootstrap = async () => {
      try {
        const { data, status } = await getMe()
        if (!cancelled) setMe(status === 200 ? data : null)
      } finally {
        if (!cancelled) setIsBootstrapping(false)
      }
    }
    bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  const value = useMemo(() => ({ me, setMe, refreshMe, logout, isBootstrapping }), [me, isBootstrapping])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
