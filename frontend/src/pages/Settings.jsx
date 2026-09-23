import { useState, useEffect, useRef, useCallback } from 'react'
import { Settings as SettingsIcon, User, Shield, Database, Save, Loader, Download, Upload, FileJson, CheckCircle, AlertCircle, Key, Eye, EyeOff, Plus, Trash2, X, Clock, Zap } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { authAPI, backupAPI, settingsAPI, configAPI, sourcesAPI } from '../services/api'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { FormSkeleton } from '../components/Skeleton'
import ConfirmDialog from '../components/ConfirmDialog'
import ScheduleFields from '../components/ScheduleFields'
import { DEFAULT_SCHEDULE } from '../components/schedule'
import { BRAND } from '../brand'

// Providers whose credentials can be verified against a live API
const TESTABLE_PROVIDERS = ['github', 'telegram']

export default function Settings() {
  const { t } = useTranslation()
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [saveStatus, setSaveStatus] = useState(null)

  // User and Settings Data
  const [user, setUser] = useState(null)
  const [settings, setSettings] = useState({
    backupBasePath: '/mnt/backup',
    maxParallelTasks: 2,
    logRetention: 30,
    backupRetentionCount: '',
    apiAuth: true,
    httpsOnly: false,
    autoCleanup: true,
  })

  // Storage Data
  const [storage, setStorage] = useState({
    totalBytes: 0,
    usedBytes: 0,
    percentage: 0,
  })

  // Password Change
  const [passwords, setPasswords] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  })
  const [passwordError, setPasswordError] = useState('')
  const [passwordSuccess, setPasswordSuccess] = useState(false)

  // Export/Import
  const fileInputRef = useRef(null)
  const [importFile, setImportFile] = useState(null)
  const [importMerge, setImportMerge] = useState(false)
  const [validationResult, setValidationResult] = useState(null)

  // Credentials
  const [credentials, setCredentials] = useState({})
  const [credentialVisibility, setCredentialVisibility] = useState({})
  const [isSavingCredentials, setIsSavingCredentials] = useState(false)
  const [newProfile, setNewProfile] = useState({ type: '', name: '', value: '' })
  const [showAddProfile, setShowAddProfile] = useState(null) // which type is adding
  const [editingProfile, setEditingProfile] = useState(null) // { provider, profile } when editing

  // Credential connection tests: which one is running, and the last result
  // per "provider:profile" key
  const [testingCredential, setTestingCredential] = useState(null)
  const [credentialTestResults, setCredentialTestResults] = useState({})

  // Global default schedule, inherited by sources without their own
  const [defaultSchedule, setDefaultSchedule] = useState(DEFAULT_SCHEDULE)
  const [isSavingSchedule, setIsSavingSchedule] = useState(false)

  // Confirm Dialogs
  const [clearBackupsConfirm, setClearBackupsConfirm] = useState(false)
  const [isClearing, setIsClearing] = useState(false)

  const loadData = useCallback(async () => {
    try {
      // Load user info
      const userRes = await authAPI.getCurrentUser()
      setUser(userRes.data)

      // Load settings from backend (includes real storage stats)
      const settingsRes = await settingsAPI.get()
      const settingsData = settingsRes.data

      // Update settings state
      setSettings({
        backupBasePath: settingsData.backup_base_path,
        maxParallelTasks: settingsData.max_parallel_tasks,
        logRetention: settingsData.log_retention_days,
        backupRetentionCount: settingsData.backup_retention_count,
        apiAuth: settingsData.api_auth_enabled,
        httpsOnly: settingsData.https_only,
        autoCleanup: settingsData.auto_cleanup,
      })

      // Update storage stats (now from real disk usage!)
      if (settingsData.storage) {
        setStorage({
          totalBytes: settingsData.storage.total_bytes,
          usedBytes: settingsData.storage.used_bytes,
          percentage: settingsData.storage.percentage_used,
        })
      }

      // Load global default schedule
      try {
        const scheduleRes = await sourcesAPI.getSchedules()
        if (scheduleRes.data?.default) setDefaultSchedule(scheduleRes.data.default)
      } catch (e) {
        console.error('Error loading default schedule:', e)
      }

      // Load credentials status
      try {
        const credRes = await settingsAPI.getCredentials()
        setCredentials(credRes.data)
      } catch (e) {
        console.error('Error loading credentials:', e)
      }

      setIsLoading(false)
    } catch (error) {
      console.error('Error loading settings:', error)
      toast.error(t('settings.loadError'))
      setIsLoading(false)
    }
  }, [t])

  useEffect(() => {
    loadData()
  }, [loadData])

  const providerLabels = {
    github: {
      label: 'GitHub',
      icon: '🔑',
      fields: {
        token: {
          label: t('credentialFields.accessToken'),
          hint: t('credentialFields.accessTokenHint')
        }
      }
    },
    nas: {
      label: 'NAS / SMB',
      icon: '💾',
      fields: {
        password: {
          label: t('credentialFields.password'),
          hint: t('credentialFields.nasPasswordHint')
        }
      }
    },
    supabase: {
      label: 'Supabase',
      icon: '⚡',
      fields: {
        connection_string: {
          label: t('credentialFields.connectionString'),
          hint: 'postgresql://postgres.xxxxx:[YOUR-PASSWORD]@aws-1-eu-north-1.pooler.supabase.com:5432/postgres',
          help: t('credentialFields.connectionHelp')
        },
        db_password: {
          label: t('credentialFields.dbPassword'),
          hint: t('credentialFields.dbPasswordHint')
        },
        service_role_key: {
          label: t('credentialFields.serviceRoleKey'),
          hint: t('credentialFields.serviceRoleHint')
        }
      }
    },
    smtp: {
      label: 'SMTP / E-Mail',
      icon: '📧',
      fields: {
        password: {
          label: t('credentialFields.password'),
          hint: t('credentialFields.emailPasswordHint')
        }
      }
    },
    telegram: {
      label: 'Telegram',
      icon: '📱',
      fields: {
        bot_token: {
          label: t('credentialFields.botToken'),
          hint: t('credentialFields.botTokenHint')
        }
      }
    },
    gdrive: {
      label: 'Google Drive',
      icon: '☁️',
      fields: {
        token: {
          label: t('credentialFields.oauthToken'),
          hint: t('credentialFields.oauthTokenHint')
        }
      }
    },
  }

  const handleAddProfile = async () => {
    if (!newProfile.name.trim()) {
      toast.error(t('settings.credentials.profileNameRequired'))
      return
    }
    const hasValues = Object.values(newProfile.values || {}).some(v => v?.trim())
    if (!hasValues) {
      toast.error(t('settings.credentials.oneFieldRequired'))
      return
    }
    setIsSavingCredentials(true)
    try {
      await settingsAPI.addCredentialProfile(showAddProfile, newProfile.name, newProfile.values)
      toast.success(t('settings.credentials.profileSaved', { name: newProfile.name }))
      setNewProfile({ name: '', values: {} })
      setShowAddProfile(null)
      setEditingProfile(null)
      const credRes = await settingsAPI.getCredentials()
      setCredentials(credRes.data)
    } catch (error) {
      toast.error(error.response?.data?.error || t('settings.credentials.saveError'))
    } finally {
      setIsSavingCredentials(false)
    }
  }

  const handleDeleteProfile = async (provider, profile) => {
    if (!confirm(t('settings.credentials.confirmDeleteProfile', { profile }))) return
    try {
      await settingsAPI.deleteCredentialProfile(provider, profile)
      toast.success(t('settings.credentials.profileDeleted', { profile }))
      const credRes = await settingsAPI.getCredentials()
      setCredentials(credRes.data)
    } catch (error) {
      toast.error(error.response?.data?.error || t('settings.credentials.deleteError'))
    }
  }

  const validatePassword = (password) => {
    if (password.length < 12) {
      return t('settings.password.minLength')
    }
    if (!/[A-Z]/.test(password)) {
      return t('settings.password.uppercase')
    }
    if (!/[a-z]/.test(password)) {
      return t('settings.password.lowercase')
    }
    if (!/\d/.test(password)) {
      return t('settings.password.digit')
    }
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
      return t('settings.password.special')
    }
    return null
  }

  const handlePasswordChange = async (e) => {
    e.preventDefault()
    setPasswordError('')
    setPasswordSuccess(false)

    // Validate passwords match
    if (passwords.newPassword !== passwords.confirmPassword) {
      setPasswordError(t('settings.password.mismatch'))
      return
    }

    // Validate password strength
    const validationError = validatePassword(passwords.newPassword)
    if (validationError) {
      setPasswordError(validationError)
      return
    }

    setIsSaving(true)
    try {
      // Call real API endpoint
      const response = await authAPI.changePassword(passwords.currentPassword, passwords.newPassword)
      if (response.data?.access_token) {
        localStorage.setItem('token', response.data.access_token)
      }
      toast.success(t('settings.password.changed'))
      setPasswordSuccess(true)
      setPasswords({ currentPassword: '', newPassword: '', confirmPassword: '' })
      setTimeout(() => setPasswordSuccess(false), 5000)
    } catch (error) {
      console.error('Error changing password:', error)
      const errorMsg = error.response?.data?.error || t('settings.password.changeError')
      setPasswordError(errorMsg)
      toast.error(errorMsg)
    } finally {
      setIsSaving(false)
    }
  }

  const handleSettingsSave = async () => {
    setIsSaving(true)
    setSaveStatus(null)
    try {
      // Call real API endpoint
      await settingsAPI.update({
        backup_base_path: settings.backupBasePath,
        max_parallel_tasks: settings.maxParallelTasks,
        log_retention_days: settings.logRetention,
        backup_retention_count: settings.backupRetentionCount,
        auto_cleanup: settings.autoCleanup,
      })
      toast.success(t('settings.saved'))
      setSaveStatus('success')
      setTimeout(() => setSaveStatus(null), 3000)
    } catch (error) {
      console.error('Error saving settings:', error)
      toast.error(t('settings.error'))
      setSaveStatus('error')
      setTimeout(() => setSaveStatus(null), 3000)
    } finally {
      setIsSaving(false)
    }
  }

  const handleTestCredential = async (provider, profile) => {
    const key = `${provider}:${profile}`
    setTestingCredential(key)
    try {
      const res = await settingsAPI.testCredential(provider, profile)
      const { success, message } = res.data
      setCredentialTestResults(prev => ({ ...prev, [key]: { success, message } }))
      success ? toast.success(message) : toast.error(message)
    } catch (error) {
      const message = error.response?.data?.error || t('settings.credentials.testError')
      setCredentialTestResults(prev => ({ ...prev, [key]: { success: false, message } }))
      toast.error(message)
    } finally {
      setTestingCredential(null)
    }
  }

  const handleScheduleSave = async () => {
    setIsSavingSchedule(true)
    try {
      const res = await sourcesAPI.updateDefaultSchedule(defaultSchedule)
      if (res.data?.schedule) setDefaultSchedule(res.data.schedule)
      toast.success(t('schedule.saved'))
    } catch (error) {
      console.error('Error saving default schedule:', error)
      toast.error(error.response?.data?.error || t('settings.error'))
    } finally {
      setIsSavingSchedule(false)
    }
  }

  const handleClearBackupsClick = () => {
    setClearBackupsConfirm(true)
  }

  const handleClearBackupsConfirm = async () => {
    setIsClearing(true)
    try {
      const response = await backupAPI.deleteAll()
      toast.success(response.data.message || t('settings.storage.clearBackupsSuccess'))
      setClearBackupsConfirm(false)
      loadData()
    } catch (error) {
      console.error('Error clearing backups:', error)
      toast.error(error.response?.data?.error || t('settings.storage.clearBackupsError'))
    } finally {
      setIsClearing(false)
    }
  }

  const handleExport = async () => {
    const loadingToast = toast.loading(t('settings.config.exporting'))
    try {
      const response = await configAPI.export()

      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url

      // Generate filename with timestamp
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0]
      link.setAttribute('download', `${BRAND.slug}_config_${timestamp}.json`)

      document.body.appendChild(link)
      link.click()
      link.parentNode.removeChild(link)
      window.URL.revokeObjectURL(url)

      toast.success(t('settings.config.exported'), { id: loadingToast })
    } catch (error) {
      console.error('Error exporting configuration:', error)
      toast.error(error.response?.data?.error || t('settings.config.exportError'), { id: loadingToast })
    }
  }

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    setImportFile(file)
    setValidationResult(null)

    // Read and validate file
    const reader = new FileReader()
    reader.onload = async (event) => {
      try {
        const configData = JSON.parse(event.target.result)

        // Validate configuration
        const response = await configAPI.validate(configData)
        setValidationResult(response.data)

        if (response.data.valid) {
          toast.success(t('settings.config.validFile'))
        } else {
          toast.error(t('settings.config.invalidFile'))
        }
      } catch (error) {
        console.error('Error validating file:', error)
        setValidationResult({
          valid: false,
          errors: [t('settings.config.invalidJson')],
          warnings: []
        })
        toast.error(t('settings.config.invalidFile'))
      }
    }
    reader.readAsText(file)
  }

  const handleImport = async () => {
    if (!importFile || !validationResult?.valid) {
      toast.error(t('settings.config.selectValidFile'))
      return
    }

    if (!confirm(t(importMerge ? 'settings.config.confirmImportMerge' : 'settings.config.confirmImportReplace'))) {
      return
    }

    const loadingToast = toast.loading(t('settings.config.importing'))
    try {
      const reader = new FileReader()
      reader.onload = async (event) => {
        try {
          const configData = JSON.parse(event.target.result)
          const response = await configAPI.import(configData, importMerge)

          toast.success(
            t('settings.config.imported', { count: response.data.summary.sources_imported }),
            { id: loadingToast }
          )

          // Reset state
          setImportFile(null)
          setValidationResult(null)
          if (fileInputRef.current) {
            fileInputRef.current.value = ''
          }

          // Reload data
          loadData()
        } catch (error) {
          console.error('Error importing configuration:', error)
          toast.error(error.response?.data?.error || t('settings.config.importError'), { id: loadingToast })
        }
      }
      reader.readAsText(importFile)
    } catch (error) {
      console.error('Error reading file:', error)
      toast.error(t('settings.config.readError'), { id: loadingToast })
    }
  }

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  const getStorageColor = () => {
    if (storage.percentage < 60) return 'bg-green-600'
    if (storage.percentage < 80) return 'bg-yellow-600'
    return 'bg-red-600'
  }

  if (isLoading) {
    return (
      <div className="page-shell">
        {/* Header Skeleton */}
        <div className="space-y-2">
          <div className="h-8 w-40 bg-gray-200 rounded animate-pulse"></div>
          <div className="h-4 w-64 bg-gray-200 rounded animate-pulse"></div>
        </div>

        {/* Settings Cards Skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 bg-gray-200 rounded-lg animate-pulse"></div>
                <div className="h-6 w-32 bg-gray-200 rounded animate-pulse"></div>
              </div>
              <FormSkeleton />
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="page-shell">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900">{t('settings.title')}</h1>
        <p className="text-sm md:text-base text-gray-600 mt-1">{t('settings.subtitle')}</p>
      </div>

      {saveStatus && (
        <div className={clsx(
          'p-3 md:p-4 rounded-lg text-sm md:text-base',
          saveStatus === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'
        )}>
          {saveStatus === 'success' ? t('settings.saved') : t('settings.error')}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        <div className="card">
          <div className="flex items-center gap-2 md:gap-3 mb-4 md:mb-6">
            <div className="p-1.5 md:p-2 bg-blue-100 rounded-lg shrink-0">
              <SettingsIcon className="w-5 h-5 md:w-6 md:h-6 text-blue-600" />
            </div>
            <h2 className="text-lg md:text-xl font-bold text-gray-900">{t('settings.general')}</h2>
          </div>
          <div className="space-y-3 md:space-y-4">
            <div>
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">{t('settings.backupBasePath')}</label>
              <input type="text" className="input" value={settings.backupBasePath} onChange={(e) => setSettings({...settings, backupBasePath: e.target.value})} />
              <p className="text-xs text-gray-500 mt-1">{t('settings.backupBasePathHint')}</p>
            </div>
            <div>
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">{t('settings.maxParallelTasks')}</label>
              <input type="number" className="input" value={settings.maxParallelTasks} onChange={(e) => setSettings({...settings, maxParallelTasks: parseInt(e.target.value)})} min="1" max="10" />
              <p className="text-xs text-gray-500 mt-1">{t('settings.maxParallelTasksHint')}</p>
            </div>
            <div>
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">{t('settings.logRetention')}</label>
              <input type="number" className="input" value={settings.logRetention} onChange={(e) => setSettings({...settings, logRetention: parseInt(e.target.value)})} min="1" />
              <p className="text-xs text-gray-500 mt-1">{t('settings.logRetentionHint')}</p>
            </div>
            <div>
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">{t('settings.backupRetentionCount')}</label>
              <input type="number" className="input" value={settings.backupRetentionCount} onChange={(e) => setSettings({...settings, backupRetentionCount: parseInt(e.target.value)})} min="1" max="1000" />
              <p className="text-xs text-gray-500 mt-1">{t('settings.backupRetentionCountHint')}</p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center gap-2 md:gap-3 mb-4 md:mb-6">
            <div className="p-1.5 md:p-2 bg-purple-100 rounded-lg shrink-0">
              <Clock className="w-5 h-5 md:w-6 md:h-6 text-purple-600" />
            </div>
            <div>
              <h2 className="text-lg md:text-xl font-bold text-gray-900">{t('schedule.defaultTitle')}</h2>
              <p className="text-xs text-gray-500">{t('schedule.defaultSubtitle')}</p>
            </div>
          </div>
          <ScheduleFields value={defaultSchedule} onChange={setDefaultSchedule} />
          <button
            type="button"
            onClick={handleScheduleSave}
            disabled={isSavingSchedule}
            className="btn btn-primary mt-4 w-full sm:w-auto"
          >
            {isSavingSchedule ? (
              <Loader className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {t('common.save')}
          </button>
        </div>

        <div className="card">
          <div className="flex items-center gap-2 md:gap-3 mb-4 md:mb-6">
            <div className="p-1.5 md:p-2 bg-green-100 rounded-lg shrink-0">
              <User className="w-5 h-5 md:w-6 md:h-6 text-green-600" />
            </div>
            <h2 className="text-lg md:text-xl font-bold text-gray-900">{t('settings.user')}</h2>
          </div>
          <form onSubmit={handlePasswordChange} className="space-y-3 md:space-y-4">
            <div>
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">{t('settings.username')}</label>
              <input type="text" className="input" value={user?.username || 'admin'} disabled />
            </div>
            <div>
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">{t('settings.currentPassword')}</label>
              <input type="password" autoComplete="current-password" className="input" placeholder={t('settings.currentPassword')} value={passwords.currentPassword} onChange={(e) => setPasswords({...passwords, currentPassword: e.target.value})} />
            </div>
            <div>
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">{t('settings.newPassword')}</label>
              <input type="password" autoComplete="new-password" className="input" placeholder={t('settings.newPassword')} value={passwords.newPassword} onChange={(e) => setPasswords({...passwords, newPassword: e.target.value})} />
            </div>
            <div>
              <label className="block text-xs md:text-sm font-medium text-gray-700 mb-2">{t('settings.confirmPassword')}</label>
              <input type="password" autoComplete="new-password" className="input" placeholder={t('settings.confirmPassword')} value={passwords.confirmPassword} onChange={(e) => setPasswords({...passwords, confirmPassword: e.target.value})} />
            </div>
            {passwordError && <p className="text-xs md:text-sm text-red-600">{passwordError}</p>}
            {passwordSuccess && <p className="text-xs md:text-sm text-green-600">{t('settings.password.changed')}</p>}
            <button type="submit" className="btn btn-primary w-full flex items-center justify-center gap-2" disabled={isSaving || !passwords.currentPassword || !passwords.newPassword || !passwords.confirmPassword}>
              {isSaving ? <><Loader className="w-4 h-4 md:w-5 md:h-5 animate-spin" /><span className="text-sm md:text-base">{t('settings.saving')}</span></> : <span className="text-sm md:text-base">{t('settings.save')}</span>}
            </button>
          </form>
        </div>

        <div className="card">
          <div className="flex items-center gap-2 md:gap-3 mb-4 md:mb-6">
            <div className="p-1.5 md:p-2 bg-red-100 rounded-lg shrink-0">
              <Shield className="w-5 h-5 md:w-6 md:h-6 text-red-600" />
            </div>
            <h2 className="text-lg md:text-xl font-bold text-gray-900">{t('settings.security.title')}</h2>
          </div>
          <div className="space-y-3 md:space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm md:text-base font-medium text-gray-900 truncate">{t('settings.security.apiAuth')}</p>
                <p className="text-xs md:text-sm text-gray-600">{t('settings.security.apiAuthHint')}</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer shrink-0">
                <input type="checkbox" className="sr-only peer" checked={settings.apiAuth} disabled />
                <div className="w-9 h-5 md:w-11 md:h-6 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 md:after:h-5 md:after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
              </label>
            </div>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm md:text-base font-medium text-gray-900 truncate">{t('settings.security.httpsOnly')}</p>
                <p className="text-xs md:text-sm text-gray-600">{t('settings.security.httpsOnlyHint')}</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer shrink-0">
                <input type="checkbox" className="sr-only peer" checked={settings.httpsOnly} onChange={(e) => setSettings({...settings, httpsOnly: e.target.checked})} />
                <div className="w-9 h-5 md:w-11 md:h-6 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 md:after:h-5 md:after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
              </label>
            </div>
          </div>
        </div>

        {/* Credentials Card */}
        <div className="card lg:col-span-2">
          <div className="flex items-center gap-2 md:gap-3 mb-4 md:mb-6">
            <div className="p-1.5 md:p-2 bg-amber-100 rounded-lg shrink-0">
              <Key className="w-5 h-5 md:w-6 md:h-6 text-amber-600" />
            </div>
            <div>
              <h2 className="text-lg md:text-xl font-bold text-gray-900">{t('settings.credentials.title')}</h2>
              <p className="text-xs text-gray-500">{t('settings.credentials.subtitle')}</p>
            </div>
          </div>
          <div className="space-y-4">
            {Object.entries(providerLabels).map(([provider, meta]) => (
              <div key={provider} className="border border-gray-200 rounded-lg p-3 md:p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-gray-800">
                    <span className="mr-2">{meta.icon}</span>{meta.label}
                  </h3>
                  <button
                    onClick={() => {
                      setShowAddProfile(showAddProfile === provider ? null : provider)
                      setNewProfile({ name: '', values: {} })
                      setEditingProfile(null)
                    }}
                    className="text-xs flex items-center gap-1 text-primary-600 hover:text-primary-800"
                  >
                    {showAddProfile === provider ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                    {showAddProfile === provider ? t('common.cancel') : t('settings.credentials.addProfile')}
                  </button>
                </div>

                {/* Existing profiles */}
                {credentials[provider]?.profiles?.length > 0 ? (
                  <div className="space-y-2">
                    {credentials[provider].profiles.map((p) => (
                      <div key={p.profile} className="bg-gray-50 rounded-lg px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium text-gray-700">{p.profile}</span>
                          <div className="flex items-center gap-1.5 shrink-0">
                            {TESTABLE_PROVIDERS.includes(provider) && (
                              <button
                                onClick={() => handleTestCredential(provider, p.profile)}
                                disabled={testingCredential === `${provider}:${p.profile}`}
                                className="text-gray-400 hover:text-green-600 disabled:opacity-50"
                                title={t('settings.credentials.testCredential')}
                              >
                                {testingCredential === `${provider}:${p.profile}` ? (
                                  <Loader className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <Zap className="w-3.5 h-3.5" />
                                )}
                              </button>
                            )}
                            {p.source === 'database' && (
                              <>
                                <button
                                  onClick={() => {
                                    setEditingProfile({ provider, profile: p.profile })
                                    setShowAddProfile(provider)
                                    setNewProfile({ name: p.profile, values: {} })
                                  }}
                                  className="text-gray-400 hover:text-blue-500"
                                  title={t('settings.credentials.editProfile')}
                                >
                                  <Save className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => handleDeleteProfile(provider, p.profile)}
                                  className="text-gray-400 hover:text-red-500"
                                  title={t('settings.credentials.deleteProfile')}
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                        {p.fields && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {Object.entries(p.fields).map(([field, configured]) => (
                              <span key={field} className={`text-xs px-1.5 py-0.5 rounded ${configured ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
                                {meta.fields[field]?.label || field}
                              </span>
                            ))}
                            <span className="text-xs text-gray-400 ml-1">{p.source}</span>
                          </div>
                        )}
                        {credentialTestResults[`${provider}:${p.profile}`] && (
                          <div className={clsx(
                            'flex items-start gap-1.5 mt-1.5 text-xs',
                            credentialTestResults[`${provider}:${p.profile}`].success
                              ? 'text-green-700' : 'text-red-600'
                          )}>
                            {credentialTestResults[`${provider}:${p.profile}`].success ? (
                              <CheckCircle className="w-3.5 h-3.5 mt-px shrink-0" />
                            ) : (
                              <AlertCircle className="w-3.5 h-3.5 mt-px shrink-0" />
                            )}
                            <span>{credentialTestResults[`${provider}:${p.profile}`].message}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-400 italic mt-1">{t('settings.credentials.noProfile')}</p>
                )}

                {/* Add/Edit profile form */}
                {showAddProfile === provider && (
                  <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg space-y-3">
                    <div className="text-xs font-semibold text-blue-700 mb-1">
                      {editingProfile ? t('settings.credentials.editProfileNamed', { profile: editingProfile.profile }) : t('settings.credentials.newProfile')}
                    </div>
                    {editingProfile && (
                      <p className="text-xs text-blue-600 italic">{t('settings.credentials.onlyFilledFields')}</p>
                    )}
                    <input
                      type="text"
                      className="input text-sm"
                      placeholder={t('settings.credentials.profileNamePlaceholder')}
                      value={newProfile.name}
                      onChange={(e) => setNewProfile({...newProfile, name: e.target.value})}
                      disabled={!!editingProfile}
                    />
                    {Object.entries(meta.fields).map(([field, fieldMeta]) => (
                      <div key={field}>
                        <label className="block text-xs font-medium text-gray-600 mb-1">{fieldMeta.label}</label>
                        <div className="relative">
                          <input
                            type={credentialVisibility[`${provider}_${field}`] ? 'text' : 'password'}
                            className="input text-sm pr-10 font-mono"
                            placeholder={fieldMeta.hint}
                            value={newProfile.values?.[field] || ''}
                            onChange={(e) => setNewProfile({
                              ...newProfile,
                              values: { ...newProfile.values, [field]: e.target.value }
                            })}
                          />
                          <button
                            type="button"
                            onClick={() => setCredentialVisibility({...credentialVisibility, [`${provider}_${field}`]: !credentialVisibility[`${provider}_${field}`]})}
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                          >
                            {credentialVisibility[`${provider}_${field}`] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                        {fieldMeta.help && (
                          <p className="text-xs text-blue-700 mt-1">{fieldMeta.help}</p>
                        )}
                      </div>
                    ))}
                    <button
                      onClick={handleAddProfile}
                      className="btn btn-primary text-sm w-full flex items-center justify-center gap-2"
                      disabled={isSavingCredentials || !newProfile.name.trim()}
                    >
                      {isSavingCredentials ? (
                        <Loader className="w-4 h-4 animate-spin" />
                      ) : (
                        <><Key className="w-4 h-4" /><span>{t('settings.credentials.saveProfile')}</span></>
                      )}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="flex items-center gap-2 md:gap-3 mb-4 md:mb-6">
            <div className="p-1.5 md:p-2 bg-purple-100 rounded-lg shrink-0">
              <Database className="w-5 h-5 md:w-6 md:h-6 text-purple-600" />
            </div>
            <h2 className="text-lg md:text-xl font-bold text-gray-900">{t('settings.storage.title')}</h2>
          </div>
          <div className="space-y-3 md:space-y-4">
            <div className="p-3 md:p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs md:text-sm text-gray-600">{t('settings.storage.usedSpace')}</span>
                <span className="text-sm md:text-base font-medium text-gray-900">
                  {formatBytes(storage.usedBytes)} / {formatBytes(storage.totalBytes)}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className={clsx('h-2 rounded-full transition-all', getStorageColor())} style={{ width: `${Math.min(storage.percentage, 100)}%` }}></div>
              </div>
              <p className="text-xs text-gray-500 mt-1">{t('settings.storage.percentUsed', { percentage: storage.percentage })}</p>
            </div>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm md:text-base font-medium text-gray-900 truncate">{t('settings.autoCleanup')}</p>
                <p className="text-xs md:text-sm text-gray-600">{t('settings.autoCleanupHint', { count: settings.backupRetentionCount })}</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer shrink-0">
                <input type="checkbox" className="sr-only peer" checked={settings.autoCleanup} onChange={(e) => setSettings({...settings, autoCleanup: e.target.checked})} />
                <div className="w-9 h-5 md:w-11 md:h-6 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 md:after:h-5 md:after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
              </label>
            </div>
            <button onClick={handleClearBackupsClick} className="btn btn-danger w-full flex items-center justify-center gap-2" disabled={isSaving}>
              <span className="text-sm md:text-base">{t('settings.storage.clearAllBackups')}</span>
            </button>
          </div>
        </div>

        {/* Export/Import Configuration Card */}
        <div className="card lg:col-span-2">
          <div className="flex items-center gap-2 md:gap-3 mb-4 md:mb-6">
            <div className="p-1.5 md:p-2 bg-indigo-100 rounded-lg shrink-0">
              <FileJson className="w-5 h-5 md:w-6 md:h-6 text-indigo-600" />
            </div>
            <h2 className="text-lg md:text-xl font-bold text-gray-900">{t('settings.config.title')}</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
            {/* Export Section */}
            <div className="space-y-3 md:space-y-4">
              <h3 className="text-base md:text-lg font-semibold text-gray-800">{t('settings.config.export')}</h3>
              <p className="text-xs md:text-sm text-gray-600">
                {t('settings.config.exportHint')}
              </p>
              <button
                onClick={handleExport}
                className="btn btn-primary w-full flex items-center justify-center gap-2"
                disabled={isSaving}
              >
                <Download className="w-4 h-4 md:w-5 md:h-5" />
                <span className="text-sm md:text-base">{t('settings.config.exportButton')}</span>
              </button>
            </div>

            {/* Import Section */}
            <div className="space-y-3 md:space-y-4">
              <h3 className="text-base md:text-lg font-semibold text-gray-800">{t('settings.config.import')}</h3>
              <p className="text-xs md:text-sm text-gray-600">
                {t('settings.config.importHint')}
              </p>

              <input
                ref={fileInputRef}
                type="file"
                accept=".json"
                onChange={handleFileSelect}
                className="hidden"
              />

              <button
                onClick={() => fileInputRef.current?.click()}
                className="btn btn-secondary w-full flex items-center justify-center gap-2"
                disabled={isSaving}
              >
                <Upload className="w-4 h-4 md:w-5 md:h-5" />
                <span className="text-sm md:text-base">
                  {importFile ? t('settings.config.selectedFile', { name: importFile.name }) : t('settings.config.chooseFile')}
                </span>
              </button>

              {validationResult && (
                <div className={clsx(
                  'p-3 rounded-lg text-xs md:text-sm',
                  validationResult.valid
                    ? 'bg-green-50 border border-green-200'
                    : 'bg-red-50 border border-red-200'
                )}>
                  <div className="flex items-start gap-2 mb-2">
                    {validationResult.valid ? (
                      <CheckCircle className="w-4 h-4 text-green-600 shrink-0 mt-0.5" />
                    ) : (
                      <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className={clsx('font-semibold', validationResult.valid ? 'text-green-800' : 'text-red-800')}>
                        {validationResult.valid ? t('settings.config.validConfiguration') : t('settings.config.invalidConfiguration')}
                      </p>
                      {validationResult.summary && (
                        <p className="text-gray-700 mt-1">
                          {t('settings.config.sourcesFound', { count: validationResult.summary.total_sources })}
                        </p>
                      )}
                    </div>
                  </div>

                  {validationResult.errors?.length > 0 && (
                    <div className="mt-2">
                      <p className="font-medium text-red-800 mb-1">{t('settings.config.errors')}</p>
                      <ul className="list-disc list-inside text-red-700 space-y-1">
                        {validationResult.errors.map((error, i) => (
                          <li key={i} className="break-words">{error}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {validationResult.warnings?.length > 0 && (
                    <div className="mt-2">
                      <p className="font-medium text-yellow-800 mb-1">{t('settings.config.warnings')}</p>
                      <ul className="list-disc list-inside text-yellow-700 space-y-1">
                        {validationResult.warnings.map((warning, i) => (
                          <li key={i} className="break-words">{warning}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {importFile && validationResult?.valid && (
                <>
                  <div className="flex items-center gap-3">
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        className="sr-only peer"
                        checked={importMerge}
                        onChange={(e) => setImportMerge(e.target.checked)}
                      />
                      <div className="w-9 h-5 md:w-11 md:h-6 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 md:after:h-5 md:after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
                    </label>
                    <div>
                      <p className="text-sm md:text-base font-medium text-gray-900">{t('settings.config.mergeMode')}</p>
                      <p className="text-xs text-gray-600">
                        {importMerge ? t('settings.config.mergeHint') : t('settings.config.replaceHint')}
                      </p>
                    </div>
                  </div>

                  <button
                    onClick={handleImport}
                    className="btn btn-primary w-full flex items-center justify-center gap-2"
                    disabled={isSaving}
                  >
                    {isSaving ? (
                      <>
                        <Loader className="w-4 h-4 md:w-5 md:h-5 animate-spin" />
                        <span className="text-sm md:text-base">{t('settings.config.importing')}</span>
                      </>
                    ) : (
                      <>
                        <Upload className="w-4 h-4 md:w-5 md:h-5" />
                        <span className="text-sm md:text-base">{t('settings.config.importButton')}</span>
                      </>
                    )}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <button onClick={handleSettingsSave} className="btn btn-primary px-6 md:px-8 flex items-center gap-2" disabled={isSaving}>
          {isSaving ? <><Loader className="w-4 h-4 md:w-5 md:h-5 animate-spin" /><span className="text-sm md:text-base">{t('settings.saving')}</span></> : <><Save className="w-4 h-4 md:w-5 md:h-5" /><span className="text-sm md:text-base">{t('settings.save')}</span></>}
        </button>
      </div>

      {/* Clear Backups Confirmation Dialog */}
      <ConfirmDialog
        isOpen={clearBackupsConfirm}
        onClose={() => setClearBackupsConfirm(false)}
        onConfirm={handleClearBackupsConfirm}
        title={t('settings.storage.clearBackupsTitle')}
        message={t('settings.storage.clearBackupsMessage')}
        confirmText={t('settings.storage.clearAllBackups')}
        cancelText={t('common.cancel')}
        confirmVariant="danger"
        isLoading={isClearing}
      />
    </div>
  )
}
