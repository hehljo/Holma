import { useState, useEffect, useRef, useCallback } from 'react'
import { Clock, CheckCircle, XCircle, AlertCircle, ChevronDown, ChevronUp, FileText, RotateCcw, Eye, EyeOff, Loader2, X } from 'lucide-react'
import { backupAPI, restoreAPI, settingsAPI } from '../services/api'
import clsx from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { useTranslation } from 'react-i18next'
import ConfirmDialog from '../components/ConfirmDialog'
import { pollRestoreStatus } from '../services/restorePolling'

export default function History() {
  const { t } = useTranslation()
  const [backups, setBackups] = useState([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [expandedLogs, setExpandedLogs] = useState({})
  const limit = 10

  // Restore state
  const [restoreModal, setRestoreModal] = useState(null) // { sourceId, sourceType, backupId }
  const [restoreBackups, setRestoreBackups] = useState([])
  const [restoreLoading, setRestoreLoading] = useState(false)
  const [restoreForm, setRestoreForm] = useState({
    backup_path: '',
    profile: '',
    target_connection_string: '',
    target_db_password: '',
    restore_storage: false,
    target_service_role_key: '',
  })
  const [supabaseProfiles, setSupabaseProfiles] = useState([])
  const [useManualConnection, setUseManualConnection] = useState(false)
  const [showRestorePassword, setShowRestorePassword] = useState(false)
  const [showServiceKey, setShowServiceKey] = useState(false)
  const [restoreStatus, setRestoreStatus] = useState(null) // null, 'starting', 'running', 'completed', 'failed'
  const [restoreResult, setRestoreResult] = useState(null)
  const [confirmRestore, setConfirmRestore] = useState(false)
  const restorePollController = useRef(null)

  const loadHistory = useCallback(async () => {
    setIsLoading(true)
    try {
      const response = await backupAPI.getHistory(limit, page * limit)
      setBackups(response.data.backups)
      setTotal(response.data.total)
      setIsLoading(false)
    } catch (error) {
      console.error('Error loading history:', error)
      setIsLoading(false)
    }
  }, [page])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  useEffect(() => () => restorePollController.current?.abort(), [])

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  const formatDuration = (seconds) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = seconds % 60

    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`
    }
    return `${secs}s`
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-green-600" />
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-600" />
      case 'partial':
        return <AlertCircle className="w-5 h-5 text-yellow-600" />
      default:
        return <Clock className="w-5 h-5 text-blue-600" />
    }
  }

  const getStatusBadge = (status) => {
    const badges = {
      completed: 'badge-success',
      running: 'badge-info',
      failed: 'badge-error',
      partial: 'badge-warning',
    }
    return badges[status] || 'badge-info'
  }

  // Restore functions
  const openRestoreModal = async (sourceId, sourceType) => {
    setRestoreModal({ sourceId, sourceType })
    setRestoreLoading(true)
    setRestoreStatus(null)
    setRestoreResult(null)
    setUseManualConnection(false)
    setRestoreForm({
      backup_path: '',
      profile: '',
      target_connection_string: '',
      target_db_password: '',
      restore_storage: false,
      target_service_role_key: '',
    })

    try {
      const [restoresRes, credsRes] = await Promise.all([
        restoreAPI.getAvailable(sourceId),
        settingsAPI.getCredentials().catch(() => ({ data: {} })),
      ])
      setRestoreBackups(restoresRes.data.backups || [])
      const profiles = credsRes.data?.supabase?.profiles || []
      setSupabaseProfiles(profiles)
      const defaultProfile = profiles[0]?.profile || ''
      setRestoreForm(prev => ({
        ...prev,
        backup_path: restoresRes.data.backups?.[0]?.path || '',
        profile: defaultProfile,
      }))
    } catch (error) {
      console.error('Error loading restore data:', error)
      setRestoreBackups([])
    }
    setRestoreLoading(false)
  }

  const handleRestore = async () => {
    setConfirmRestore(false)
    setRestoreStatus('starting')

    try {
      const response = await restoreAPI.start(restoreForm)
      const restoreId = response.data.restore_id
      restorePollController.current?.abort()
      const controller = new AbortController()
      restorePollController.current = controller
      const result = await pollRestoreStatus(restoreId, {
        signal: controller.signal,
        onUpdate: data => {
          setRestoreStatus(data.status === 'queued' ? 'starting' : data.status)
          setRestoreResult(data)
        },
      })
      setRestoreStatus(result.status)
      setRestoreResult(result)
    } catch (error) {
      if (error.name === 'CanceledError' || error.name === 'AbortError') return
      setRestoreStatus('failed')
      setRestoreResult({ error: error.response?.data?.error || t('restore.genericError') })
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">{t('common.loading')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="page-shell">
      {/* Header */}
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900">{t('history.title')}</h1>
        <p className="text-sm md:text-base text-gray-600 mt-1">{t('history.subtitle')}</p>
      </div>

      {/* History List */}
      <div className="space-y-3 md:space-y-4">
        {backups.map((backup) => (
          <div key={backup.backup_id} className="card">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                {getStatusIcon(backup.status)}
                <div>
                  <p className="font-semibold text-gray-900">
                    Backup {backup.backup_id.substring(0, 8)}
                  </p>
                  <p className="text-sm text-gray-600">
                    {formatDistanceToNow(new Date(backup.started_at), { addSuffix: true })}
                  </p>
                </div>
              </div>
              <span className={clsx('badge', getStatusBadge(backup.status))}>
                {t(`dashboard.status.${backup.status}`)}
              </span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4 mb-3 md:mb-4">
              <div>
                <p className="text-xs md:text-sm text-gray-600">{t('history.started')}</p>
                <p className="text-sm md:text-base font-medium text-gray-900 truncate">
                  {new Date(backup.started_at).toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-xs md:text-sm text-gray-600">{t('history.duration')}</p>
                <p className="text-sm md:text-base font-medium text-gray-900">
                  {backup.duration ? formatDuration(backup.duration) : 'N/A'}
                </p>
              </div>
              <div>
                <p className="text-xs md:text-sm text-gray-600">{t('history.sources')}</p>
                <p className="text-sm md:text-base font-medium text-gray-900">{backup.sources_count}</p>
              </div>
              <div>
                <p className="text-xs md:text-sm text-gray-600">{t('history.totalSize')}</p>
                <p className="text-sm md:text-base font-medium text-gray-900">{formatBytes(backup.total_size)}</p>
              </div>
            </div>

            {/* Backup-level error message */}
            {backup.error_message && (
              <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm font-medium text-red-800 mb-1">{t('common.error')}:</p>
                <pre className="text-xs text-red-700 font-mono whitespace-pre-wrap">{backup.error_message}</pre>
              </div>
            )}

            {backup.sources && backup.sources.length > 0 && (
              <div className="border-t border-gray-200 pt-4">
                <p className="text-sm font-medium text-gray-700 mb-3">{t('history.sourceDetails')}</p>
                <div className="space-y-2">
                  {backup.sources.map((source) => (
                    <div key={source.source_id} className="bg-gray-50 rounded-lg overflow-hidden">
                      <div className="flex items-center justify-between text-sm p-3">
                        <div className="flex items-center gap-3">
                          <div className={clsx(
                            'w-2 h-2 rounded-full',
                            source.status === 'completed' ? 'bg-green-500' :
                            source.status === 'failed' ? 'bg-red-500' :
                            'bg-blue-500'
                          )}></div>
                          <span className="font-medium">{source.source_name}</span>
                          <span className="text-gray-500">({source.source_type})</span>
                        </div>
                        <div className="flex items-center gap-2 md:gap-4 flex-wrap justify-end">
                          <span className="text-gray-600 text-xs md:text-sm">
                            {source.files_synced} files • {formatBytes(source.size_synced)}
                          </span>
                          <span className={clsx('badge text-xs', getStatusBadge(source.status))}>
                            {t(`dashboard.status.${source.status}`)}
                          </span>
                          {/* Restore Button for Supabase sources */}
                          {source.source_type === 'supabase' && source.status === 'completed' && (
                            <button
                              onClick={() => openRestoreModal(source.source_id, source.source_type)}
                              className="flex items-center gap-1 text-blue-600 hover:text-blue-800 text-xs font-medium"
                              title={t('restore.action')}
                            >
                              <RotateCcw className="w-3.5 h-3.5" />
                              {t('restore.action')}
                            </button>
                          )}
                          <button
                            onClick={() => setExpandedLogs(prev => ({
                              ...prev,
                              [`${backup.backup_id}-${source.source_id}`]: !prev[`${backup.backup_id}-${source.source_id}`]
                            }))}
                            className="flex items-center gap-1 text-gray-500 hover:text-gray-700 text-xs"
                            title={t('restore.logs')}
                          >
                            <FileText className="w-3.5 h-3.5" />
                            {expandedLogs[`${backup.backup_id}-${source.source_id}`] ? (
                              <ChevronUp className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronDown className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>
                      </div>
                      {expandedLogs[`${backup.backup_id}-${source.source_id}`] && (
                        <div className="border-t border-gray-200 p-3">
                          {source.error_message && (
                            <div className="mb-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700 font-mono whitespace-pre-wrap">
                              {source.error_message}
                            </div>
                          )}
                          {source.logs ? (
                            <pre className="text-xs text-gray-600 font-mono whitespace-pre-wrap max-h-64 overflow-y-auto bg-white p-2 rounded border">
                              {source.logs}
                            </pre>
                          ) : !source.error_message && (
                            <p className="text-xs text-gray-400 italic">{t('restore.noLogs')}</p>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {backups.length === 0 && (
        <div className="card text-center py-12">
          <Clock className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-900 mb-2">{t('history.noHistory')}</h3>
          <p className="text-gray-600">{t('dashboard.startBackup')}</p>
        </div>
      )}

      {/* Pagination */}
      {total > limit && (
        <div className="flex flex-col sm:flex-row items-center justify-center gap-2 md:gap-3">
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            className="btn btn-secondary disabled:opacity-50 w-full sm:w-auto"
          >
            {t('history.previous')}
          </button>
          <span className="text-sm md:text-base text-gray-600">
            {t('history.page', { current: page + 1, total: Math.ceil(total / limit) })}
          </span>
          <button
            onClick={() => setPage(page + 1)}
            disabled={(page + 1) * limit >= total}
            className="btn btn-secondary disabled:opacity-50 w-full sm:w-auto"
          >
            {t('history.next')}
          </button>
        </div>
      )}

      {/* Restore Modal */}
      {restoreModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="fixed inset-0 bg-black/50" onClick={() => !restoreStatus && setRestoreModal(null)} />

          <div className="flex min-h-full items-center justify-center p-4">
            <div className="relative bg-white rounded-xl shadow-xl w-full max-w-lg">
              {/* Header */}
              <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between rounded-t-xl">
                <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                  <RotateCcw className="w-5 h-5" />
                  {t('restore.title')}
                </h2>
                {!restoreStatus && (
                  <button onClick={() => setRestoreModal(null)} className="p-2 hover:bg-gray-100 rounded-lg" aria-label={t('common.close')}>
                    <X className="w-5 h-5" />
                  </button>
                )}
              </div>

              <div className="p-6 space-y-4">
                {/* Restore Status Display */}
                {restoreStatus && (
                  <div className={clsx(
                    'p-4 rounded-lg border',
                    restoreStatus === 'running' || restoreStatus === 'starting' ? 'bg-blue-50 border-blue-200' :
                    restoreStatus === 'completed' ? 'bg-green-50 border-green-200' :
                    restoreStatus === 'partial' ? 'bg-yellow-50 border-yellow-200' :
                    'bg-red-50 border-red-200'
                  )}>
                    <div className="flex items-center gap-3">
                      {(restoreStatus === 'running' || restoreStatus === 'starting') && (
                        <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
                      )}
                      {restoreStatus === 'completed' && <CheckCircle className="w-5 h-5 text-green-600" />}
                      {restoreStatus === 'partial' && <AlertCircle className="w-5 h-5 text-yellow-600" />}
                      {restoreStatus === 'failed' && <XCircle className="w-5 h-5 text-red-600" />}
                      <div>
                        <p className="font-semibold text-gray-900">
                          {t(`restore.${restoreStatus}`)}
                        </p>
                        {restoreResult?.steps_total && (
                          <p className="text-sm text-gray-600">
                            {t('restore.steps', {
                              completed: restoreResult.steps_completed,
                              total: restoreResult.steps_total,
                            })}
                          </p>
                        )}
                      </div>
                    </div>

                    {restoreResult?.errors?.length > 0 && (
                      <div className="mt-3 space-y-1">
                        {restoreResult.errors.map((err, i) => (
                          <p key={i} className="text-xs text-red-700">{err}</p>
                        ))}
                      </div>
                    )}

                    {restoreResult?.error && (
                      <p className="mt-2 text-sm text-red-700">{restoreResult.error}</p>
                    )}

                    {restoreResult?.logs && (
                      <pre className="mt-3 text-xs text-gray-600 font-mono whitespace-pre-wrap max-h-48 overflow-y-auto bg-white p-2 rounded border">
                        {restoreResult.logs}
                      </pre>
                    )}

                    {(restoreStatus === 'completed' || restoreStatus === 'partial' || restoreStatus === 'failed') && (
                      <button
                        onClick={() => { setRestoreModal(null); setRestoreStatus(null); setRestoreResult(null) }}
                        className="mt-3 btn btn-secondary text-sm"
                      >
                        {t('common.close')}
                      </button>
                    )}
                  </div>
                )}

                {/* Restore Form */}
                {!restoreStatus && (
                  <>
                    <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                      <p className="text-sm text-amber-800">
                        {t('restore.safetyWarning')}
                      </p>
                    </div>

                    {/* Backup Selection */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">{t('restore.selectBackup')}</label>
                      {restoreLoading ? (
                        <div className="flex items-center gap-2 text-gray-500">
                          <Loader2 className="w-4 h-4 animate-spin" /> {t('restore.loadingBackups')}
                        </div>
                      ) : restoreBackups.length === 0 ? (
                        <p className="text-sm text-gray-500">{t('restore.noBackups')}</p>
                      ) : (
                        <select
                          className="input"
                          value={restoreForm.backup_path}
                          onChange={(e) => setRestoreForm(prev => ({ ...prev, backup_path: e.target.value }))}
                        >
                          {restoreBackups.map((b) => (
                            <option key={b.path} value={b.path}>
                              {b.filename} ({formatBytes(b.size)}) - {new Date(b.created).toLocaleString()}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>

                    {/* Profile / Manual Connection */}
                    {!useManualConnection ? (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">{t('restore.targetProfile')}</label>
                        {supabaseProfiles.length === 0 ? (
                          <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                            <p className="text-sm text-amber-800">
                              {t('restore.noProfileManual')}
                            </p>
                          </div>
                        ) : (
                          <>
                            <select
                              className="input"
                              value={restoreForm.profile}
                              onChange={(e) => setRestoreForm(prev => ({ ...prev, profile: e.target.value }))}
                            >
                              {supabaseProfiles.map((p) => (
                                <option key={p.profile} value={p.profile}>{p.profile}</option>
                              ))}
                            </select>
                            <p className="text-xs text-gray-500 mt-1">
                              {t('restore.profileHint')}
                            </p>
                          </>
                        )}
                        <button
                          type="button"
                          onClick={() => setUseManualConnection(true)}
                          className="mt-2 text-xs text-blue-600 hover:text-blue-800 underline"
                        >
                          {t('restore.manualConnection')}
                        </button>
                      </div>
                    ) : (
                      <>
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <label className="block text-sm font-medium text-gray-700">{t('restore.connectionString')}</label>
                            <button
                              type="button"
                              onClick={() => setUseManualConnection(false)}
                              className="text-xs text-blue-600 hover:text-blue-800 underline"
                            >
                              {t('restore.useProfile')}
                            </button>
                          </div>
                          <input
                            type="text"
                            className="input font-mono text-sm"
                            value={restoreForm.target_connection_string}
                            onChange={(e) => setRestoreForm(prev => ({ ...prev, target_connection_string: e.target.value }))}
                            placeholder="postgresql://postgres.xxxxx:[YOUR-PASSWORD]@aws-1-eu-north-1.pooler.supabase.com:5432/postgres"
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            Aus dem Supabase Dashboard des Ziel-Projekts → Session Pooler URI kopieren
                          </p>
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-2">{t('restore.dbPassword')}</label>
                          <div className="relative">
                            <input
                              type={showRestorePassword ? "text" : "password"}
                              className="input pr-10"
                              value={restoreForm.target_db_password}
                              onChange={(e) => setRestoreForm(prev => ({ ...prev, target_db_password: e.target.value }))}
                              placeholder={t('restore.dbPasswordPlaceholder')}
                            />
                            <button
                              type="button"
                              onClick={() => setShowRestorePassword(!showRestorePassword)}
                              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700"
                            >
                              {showRestorePassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                            </button>
                          </div>
                        </div>
                      </>
                    )}

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                        checked={restoreForm.restore_storage}
                        onChange={(e) => setRestoreForm(prev => ({ ...prev, restore_storage: e.target.checked }))}
                      />
                      <span className="text-sm text-gray-700">{t('restore.storage')}</span>
                    </label>

                    {restoreForm.restore_storage && useManualConnection && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">{t('restore.serviceRoleKey')}</label>
                        <div className="relative">
                          <input
                            type={showServiceKey ? "text" : "password"}
                            className="input pr-10"
                            value={restoreForm.target_service_role_key}
                            onChange={(e) => setRestoreForm(prev => ({ ...prev, target_service_role_key: e.target.value }))}
                            placeholder="eyJ..."
                          />
                          <button
                            type="button"
                            onClick={() => setShowServiceKey(!showServiceKey)}
                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700"
                          >
                            {showServiceKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex gap-3 pt-2">
                      <button
                        onClick={() => setRestoreModal(null)}
                        className="btn btn-secondary flex-1"
                      >
                        {t('common.cancel')}
                      </button>
                      <button
                        onClick={() => setConfirmRestore(true)}
                        disabled={
                          !restoreForm.backup_path ||
                          (useManualConnection
                            ? !restoreForm.target_connection_string
                            : !restoreForm.profile)
                        }
                        className="btn btn-primary flex-1 disabled:opacity-50"
                      >
                        <RotateCcw className="w-4 h-4 mr-2" />
                        {t('restore.start')}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Dialog */}
      <ConfirmDialog
        isOpen={confirmRestore}
        title={t('restore.confirmTitle')}
        message={`${t('restore.confirmMessage')} ${restoreForm.restore_storage ? t('restore.storageWarning') : ''} ${t('restore.confirmContinue')}`}
        confirmText={t('restore.confirmStart')}
        cancelText={t('common.cancel')}
        onConfirm={handleRestore}
        onClose={() => setConfirmRestore(false)}
        confirmVariant="danger"
      />
    </div>
  )
}
