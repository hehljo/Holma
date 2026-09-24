import { useEffect, useState } from 'react'
import { AlertCircle } from 'lucide-react'
import { authAPI } from '../services/api'
import { useTranslation } from 'react-i18next'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { BrandLogo } from '../components/BrandLogo'
import PropTypes from 'prop-types'

export default function Login({ onLogin }) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [needsSetup, setNeedsSetup] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    let active = true
    authAPI.setupStatus()
      .then(({ data }) => { if (active) setNeedsSetup(data.needs_setup) })
      .catch(() => { if (active) setError(t('login.statusError')) })
    return () => { active = false }
  }, [t])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (needsSetup && password !== confirmPassword) {
      setError(t('login.passwordMismatch'))
      return
    }
    setIsLoading(true)

    try {
      if (needsSetup) {
        await authAPI.setupOwner(username, password, confirmPassword)
      }
      const response = await authAPI.login(username, password)
      localStorage.setItem('token', response.data.access_token)
      onLogin()
    } catch (err) {
      setError(err.response?.data?.error || t(needsSetup ? 'login.setupFailed' : 'login.failed'))
      if (needsSetup) {
        authAPI.setupStatus().then(({ data }) => setNeedsSetup(data.needs_setup)).catch(() => {})
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-primary-100 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl p-8 w-full max-w-md">
        {/* Language Switcher */}
        <div className="flex justify-end mb-4">
          <LanguageSwitcher />
        </div>

        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <BrandLogo className="h-20 w-auto mb-3 text-primary-600" />
          <h1 className="text-3xl font-bold text-gray-900">{t('app.name')}</h1>
          <p className="text-gray-600 mt-2">{t('app.tagline')}</p>
        </div>

        {needsSetup && (
          <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
            <p className="font-semibold">{t('login.setupTitle')}</p>
            <p className="mt-2">{t('login.setupHelp')}</p>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        {/* Login form */}
        {needsSetup !== null && <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="login-username" className="block text-sm font-medium text-gray-700 mb-2">
              {t('login.username')}
            </label>
            <input
              id="login-username"
              type="text"
              autoComplete="username"
              minLength={needsSetup ? 3 : undefined}
              maxLength={needsSetup ? 80 : undefined}
              pattern={needsSetup ? '[A-Za-z0-9_.-]{3,80}' : undefined}
              title={needsSetup ? t('login.usernameRules') : undefined}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="input"
              placeholder={t('login.username')}
              required
              disabled={isLoading}
            />
          </div>

          <div>
            <label htmlFor="login-password" className="block text-sm font-medium text-gray-700 mb-2">
              {t('login.password')}
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete={needsSetup ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
              placeholder={t('login.password')}
              required
              disabled={isLoading}
            />
          </div>

          {needsSetup && (
            <>
              <p className="text-sm text-gray-600">{t('login.usernameRules')}</p>
              <p className="text-sm text-gray-600">{t('login.passwordRules')}</p>
              <div>
                <label htmlFor="login-confirm" className="block text-sm font-medium text-gray-700 mb-2">{t('login.confirmPassword')}</label>
                <input id="login-confirm" type="password" autoComplete="new-password" className="input"
                  value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required disabled={isLoading} />
              </div>
            </>
          )}
          <button type="submit" className="btn btn-primary w-full mt-6" disabled={isLoading}>
            {isLoading ? t('login.loggingIn') : t(needsSetup ? 'login.createOwner' : 'login.loginButton')}
          </button>
        </form>}
      </div>
    </div>
  )
}

Login.propTypes = {
  onLogin: PropTypes.func.isRequired,
}
