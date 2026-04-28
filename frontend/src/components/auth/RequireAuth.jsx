import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './auth-context'

function RequireAuth({ children, roles }) {
  const { me, isBootstrapping } = useAuth()
  const location = useLocation()

  if (isBootstrapping) return <div className="p-6 text-sm">Loading account...</div>
  if (!me) return <Navigate to="/auth/login" replace state={{ from: location.pathname }} />
  if (roles && !roles.includes(me.role)) return <Navigate to="/" replace />
  return children
}

export default RequireAuth
