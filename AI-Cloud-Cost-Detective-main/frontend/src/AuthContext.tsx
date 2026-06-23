import { createContext, useContext, useState, type ReactNode } from 'react'
import { auth } from './api'
import type { User } from './types'

interface AuthContextType {
  token: string | null
  user: User | null
  login: (token: string, user: User) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType>(null!)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'))
  const [user, setUser] = useState<User | null>(() => {
    try {
      const raw = localStorage.getItem('user')
      if (!raw) return null
      const parsed = JSON.parse(raw)
      if (!parsed || typeof parsed.id !== 'number' || typeof parsed.email !== 'string') {
        localStorage.removeItem('user')
        localStorage.removeItem('token')
        return null
      }
      return parsed
    } catch {
      localStorage.removeItem('user')
      localStorage.removeItem('token')
      return null
    }
  })

  const login = (t: string, u: User) => {
    localStorage.setItem('token', t)
    localStorage.setItem('user', JSON.stringify(u))
    setToken(t)
    setUser(u)
  }

  const logout = () => {
    // Revoke the token server-side (best-effort — clear locally regardless)
    auth.logout().catch(() => {})
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
