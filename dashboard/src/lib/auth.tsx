import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

export type Role = 'admin' | 'analyst' | 'agent'

export interface AuthUser {
  name: string
  role: Role
  email: string
}

interface AuthContextValue {
  user: AuthUser | null
  login: (user: AuthUser) => void
  logout: () => void
}

const STORAGE_KEY = 'propertylead:user'

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

function readStoredUser(): AuthUser | null {
  if (typeof window === 'undefined') {
    return null
  }

  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (!stored) {
    return null
  }

  try {
    return JSON.parse(stored) as AuthUser
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => readStoredUser())

  const login = (nextUser: AuthUser) => {
    setUser(nextUser)
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextUser))
  }

  const logout = () => {
    setUser(null)
    window.localStorage.removeItem(STORAGE_KEY)
  }

  const value = useMemo<AuthContextValue>(() => ({ user, login, logout }), [user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
