import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AccountPage from './components/auth/AccountPage'
import AdminHomePage from './components/auth/AdminHomePage'
import LoginPage from './components/auth/LoginPage'
import OperatorHomePage from './components/auth/OperatorHomePage'
import RegisterPage from './components/auth/RegisterPage'
import RequireAuth from './components/auth/RequireAuth'
import { AuthProvider } from './components/auth/auth-context'
import DashboardHome from './components/dashboard/DashboardHome'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/auth/login" element={<LoginPage />} />
          <Route path="/auth/register" element={<RegisterPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <DashboardHome />
              </RequireAuth>
            }
          />
          <Route
            path="/account"
            element={
              <RequireAuth>
                <AccountPage />
              </RequireAuth>
            }
          />
          <Route
            path="/operator/home"
            element={
              <RequireAuth roles={['OPERATOR', 'ADMIN', 'OWNER']}>
                <OperatorHomePage />
              </RequireAuth>
            }
          />
          <Route
            path="/admin/home"
            element={
              <RequireAuth roles={['ADMIN', 'OWNER']}>
                <AdminHomePage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
