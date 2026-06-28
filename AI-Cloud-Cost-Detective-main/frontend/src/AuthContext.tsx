import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { auth } from './api'
import type { User } from './types'

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (user: User) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType>(null!)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // On mount: re-hydrate auth state from the httpOnly cookie via /api/auth/me
  useEffect(() => {
    auth.me()
      .then(u => setUser({ id: u.id, email: u.email }))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = (u: User) => setUser(u)

  const logout = () => {
    auth.logout().catch(() => {})
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
