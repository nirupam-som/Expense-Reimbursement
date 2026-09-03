import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { clearToken, getToken, setToken } from '../api/client.js'
import * as api from '../api/endpoints.js'

const AuthContext = createContext(null)

/**
 * Holds the signed-in user.
 *
 * The token is kept in localStorage so a refresh doesn't sign you out, but the *user* is
 * always re-fetched from /auth/me rather than decoded from the token client-side: the
 * server is the only thing that decides who you are and what role you hold.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(getToken()))

  useEffect(() => {
    if (!getToken()) {
      setLoading(false)
      return
    }
    api
      .me()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setLoading(false))
  }, [])

  const signIn = useCallback(async (email, password) => {
    const response = await api.login(email, password)
    setToken(response.access_token)
    setUser(response.user)
    return response.user
  }, [])

  const register = useCallback(async (payload) => {
    const response = await api.signup(payload)
    setToken(response.access_token)
    setUser(response.user)
    return response.user
  }, [])

  const signOut = useCallback(() => {
    clearToken()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, signIn, register, signOut, isApprover: user?.role === 'approver' }),
    [user, loading, signIn, register, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside an AuthProvider')
  return context
}
