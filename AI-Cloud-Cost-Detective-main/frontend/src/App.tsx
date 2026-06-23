import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { ThemeProvider } from './ThemeContext'
import Navbar from './components/Navbar'
import Analyze from './pages/Analyze'
import ChangePassword from './pages/ChangePassword'
import Dashboard from './pages/Dashboard'
import History from './pages/History'
import Login from './pages/Login'
import Report from './pages/Report'
import Signup from './pages/Signup'
import type { ReactNode } from 'react'

function Private({ children }: { children: ReactNode }) {
  const { token } = useAuth()
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  const { token } = useAuth()

  return (
    <ThemeProvider>
      <div className="min-h-screen flex flex-col">
        {token && <Navbar />}
        <main className="flex-1">
          <Routes>
            <Route path="/login" element={token ? <Navigate to="/" replace /> : <Login />} />
            <Route path="/signup" element={token ? <Navigate to="/" replace /> : <Signup />} />
            <Route path="/" element={<Private><Dashboard /></Private>} />
            <Route path="/analyze/:id" element={<Private><Analyze /></Private>} />
            <Route path="/report/:id" element={<Private><Report /></Private>} />
            <Route path="/history" element={<Private><History /></Private>} />
            <Route path="/change-password" element={<Private><ChangePassword /></Private>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </ThemeProvider>
  )
}
