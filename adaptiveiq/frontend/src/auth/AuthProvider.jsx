import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { setUnauthorizedHandler } from '../api/client'
import { authApi } from '../api/endpoints'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined)            // undefined = still checking, null = signed out

  useEffect(() => {
    authApi.me().then(setUser).catch(() => setUser(null))
    setUnauthorizedHandler(() => setUser(null))
  }, [])

  const login = useCallback(async (email, password) => {
    const u = await authApi.login(email, password)
    setUser(u)
    return u
  }, [])
  const register = useCallback(async (body) => {
    const u = await authApi.register(body)
    setUser(u)
    return u
  }, [])
  const logout = useCallback(async () => {
    try { await authApi.logout() } finally { setUser(null) }
  }, [])

  const value = useMemo(() => ({ user, setUser, login, register, logout, checking: user === undefined }),
    [user, login, register, logout])
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)

export const homeFor = (user) => (user?.role === 'lecturer' ? '/lecturer' : '/student')
