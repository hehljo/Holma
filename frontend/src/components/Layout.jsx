import { Link, useLocation } from 'react-router-dom'
import { Home, Database, History, Settings, LogOut, Menu, X, Bell, FileText, Archive, Moon, Sun } from 'lucide-react'
import clsx from 'clsx'
import { useTranslation } from 'react-i18next'
import { useState, useEffect } from 'react'
import LanguageSwitcher from './LanguageSwitcher'
import PropTypes from 'prop-types'

const navigation = [
  { name: 'dashboard', href: '/', icon: Home },
  { name: 'sources', href: '/sources', icon: Database },
  { name: 'backups', href: '/backups', icon: Archive },
  { name: 'history', href: '/history', icon: History },
  { name: 'notifications', href: '/notifications', icon: Bell },
  { name: 'logs', href: '/logs', icon: FileText },
  { name: 'settings', href: '/settings', icon: Settings },
]

export default function Layout({ children, onLogout, isDarkMode, onToggleDarkMode }) {
  const location = useLocation()
  const { t } = useTranslation()
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  // Close mobile menu when route changes
  useEffect(() => {
    setIsMobileMenuOpen(false)
  }, [location.pathname])

  // Prevent scroll when mobile menu is open
  useEffect(() => {
    if (isMobileMenuOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = 'unset'
    }
    return () => {
      document.body.style.overflow = 'unset'
    }
  }, [isMobileMenuOpen])

  const SidebarContent = () => (
    <>
      {/* Logo */}
      <div className="px-5 py-5 border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-center gap-3">
          <img src="/logo-mark.png" alt="" className="h-10 w-9 object-contain shrink-0" />
          <div className="min-w-0">
            <h1 className="truncate text-xl font-bold text-gray-900">{t('app.name')}</h1>
            <p className="truncate text-xs text-gray-500">{t('app.shortDescription')}</p>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-[1fr_auto] items-center gap-2">
          <LanguageSwitcher />
          <button
            type="button"
            onClick={onToggleDarkMode}
            className="icon-btn text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800"
            aria-label={isDarkMode ? t('theme.light') : t('theme.dark')}
            title={isDarkMode ? t('theme.light') : t('theme.dark')}
          >
            {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href
          const Icon = item.icon

          return (
            <Link
              key={item.name}
              to={item.href}
              className={clsx(
                'flex min-h-11 items-center gap-3 rounded-lg px-4 py-2.5 transition-all',
                isActive
                  ? 'bg-primary-50 text-primary-700 font-medium'
                  : 'text-gray-700 hover:bg-gray-100'
              )}
            >
              <Icon className="w-5 h-5 shrink-0" />
              <span className="truncate">{t(`nav.${item.name}`)}</span>
            </Link>
          )
        })}
      </nav>

      {/* Logout + Version */}
      <div className="p-4 border-t border-gray-200 dark:border-gray-800">
        <button
          onClick={onLogout}
          className="flex min-h-11 w-full items-center gap-3 rounded-lg px-4 py-2.5 text-red-600 transition-all hover:bg-red-50 dark:hover:bg-red-950/40"
        >
          <LogOut className="w-5 h-5" />
          {t('nav.logout')}
        </button>
        <p className="text-xs text-gray-400 text-center mt-2">v1.7.0</p>
      </div>
    </>
  )

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 transition-colors">
      {/* Mobile Header */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 bg-white/95 dark:bg-gray-900/95 backdrop-blur border-b border-gray-200 dark:border-gray-800">
        <div className="flex min-h-16 items-center justify-between px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <img src="/logo-mark.png" alt="" className="h-9 w-8 object-contain shrink-0" />
            <h1 className="truncate text-lg font-bold text-gray-900">{t('app.name')}</h1>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onToggleDarkMode}
              className="icon-btn text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800"
              aria-label={isDarkMode ? t('theme.light') : t('theme.dark')}
              title={isDarkMode ? t('theme.light') : t('theme.dark')}
            >
              {isDarkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="icon-btn hover:bg-gray-100 dark:hover:bg-gray-800"
              aria-label={t('nav.toggleMenu')}
            >
              {isMobileMenuOpen ? (
                <X className="w-6 h-6 text-gray-700 dark:text-gray-200" />
              ) : (
                <Menu className="w-6 h-6 text-gray-700 dark:text-gray-200" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Menu Backdrop */}
      {isMobileMenuOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 z-40 transition-opacity"
          onClick={() => setIsMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile Sidebar Drawer */}
      <div
        className={clsx(
          'md:hidden fixed inset-y-0 left-0 z-50 w-[min(20rem,calc(100vw-2rem))] bg-white shadow-2xl transform transition-transform duration-300 ease-in-out flex flex-col',
          'dark:bg-gray-900 dark:border-r dark:border-gray-800',
          isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <SidebarContent />
      </div>

      {/* Desktop Sidebar */}
      <div className="hidden md:flex md:fixed md:inset-y-0 md:left-0 md:w-64 md:flex-col bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800">
        <SidebarContent />
      </div>

      {/* Main content */}
      <div className="md:pl-64 pt-16 md:pt-0">
        <main className="px-3 py-4 sm:px-4 md:p-8">
          {children}
        </main>
      </div>
    </div>
  )
}

Layout.propTypes = {
  children: PropTypes.node.isRequired,
  onLogout: PropTypes.func.isRequired,
  isDarkMode: PropTypes.bool.isRequired,
  onToggleDarkMode: PropTypes.func.isRequired,
}
