import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Archive, Search, RotateCcw, CheckCircle, XCircle, AlertCircle,
  Clock, ChevronDown, ChevronUp, FileText, X, Loader2, Eye, EyeOff,
  HardDrive, Database, RefreshCw, Calendar, SlidersHorizontal, Download
} from 'lucide-react'
import { backupAPI, restoreAPI, settingsAPI, downloadAPI } from '../services/api'
import clsx from 'clsx'
import { formatDistanceToNow, format } from 'date-fns'
import { useTranslation } from 'react-i18next'
import ConfirmDialog from '../components/ConfirmDialog'
import { pollRestoreStatus } from '../services/restorePolling'

const STATUS_ALL = 'all'
const STATUS_RESTORABLE = 'restorable'

const RESTORABLE_TYPES = ['supabase']

export default function Backups() {
  const { t } = useTranslation()

  // Data
  const [allBackups, setAllBackups] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const limit = 50

  // Filters
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState(STATUS_ALL)
  const [typeFilter, setTypeFilter] = useState(STATUS_ALL)
  const [quickFilter, setQuickFilter] = useState(null) // 'restorable' | null
  const [expandedLogs, setExpandedLogs] = useState({})

  // Download
  const [downloadModal, setDownloadModal] = useState(null) // { sourceId, sourceName }
  const [downloadFiles, setDownloadFiles] = useState([])
  const [downloadLoading, setDownloadLoading] = useState(false)

  const openDownloadModal = async (sourceId, sourceName) => {
    setDownloadModal({ sourceId, sourceName })
    setDownloadLoading(true)
    setDownloadFiles([])
    try {
      const res = await downloadAPI.listFiles(sourceId)
      setDownloadFiles(res.data.files || [])
    } catch (_error) {
      setDownloadFiles([])
    }
    setDownloadLoading(false)
  }

  const triggerDownload = (sourceId, filename) => {
    const token = localStorage.getItem('token')
    const url = downloadAPI.getDownloadUrl(sourceId, filename)
    // Use fetch to include auth header, then trigger blob download
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = filename.endsWith('.git') ? filename + '.tar.gz' : filename
        a.click()
        URL.revokeObjectURL(a.href)
      })
  }

  // Restore
  const [restoreModal, setRestoreModal] = useState(null)
  const [restoreBackups, setRestoreBackups] = useState([])
  const [restoreLoading, setRestoreLoading] = useState(false)
  const [restoreForm, setRestoreForm] = useState({
    backup_path: '', profile: '', target_connection_string: '',
    target_db_password: '', restore_storage: false, target_service_role_key: '',
  })
  const [supabaseProfiles, setSupabaseProfiles] = useState([])
  const [useManualConnection, setUseManualConnection] = useState(false)
  const [showRestorePassword, setShowRestorePassword] = useState(false)
  const [showServiceKey, setShowServiceKey] = useState(false)
  const [restoreStatus, setRestoreStatus] = useState(null)
  const [restoreResult, setRestoreResult] = useState(null)
  const [confirmRestore, setConfirmRestore] = useState(false)
  const restorePollController = useRef(null)

  const loadBackups = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await backupAPI.getHistory(limit, page * limit)
      setAllBackups(res.data.backups || [])
      setTotal(res.data.total || 0)
    } catch (e) {
      console.error(e)
    }
    setIsLoading(false)
  }, [page])

  useEffect(() => { loadBackups() }, [loadBackups])
  useEffect(() => () => restorePollController.current?.abort(), [])

  // ── Derived: flatten to source-level rows ──────────────────────────────────
  const rows = []
  for (const backup of allBackups) {
    if (!backup.sources?.length) {
      rows.push({ backup, source: null })
    } else {
      for (const source of backup.sources) {
        rows.push({ backup, source })
      }
    }
  }

  const sourceTypes = [...new Set(rows.map(r => r.source?.source_type).filter(Boolean))]

  const filtered = rows.filter(({ backup, source }) => {
    const q = search.toLowerCase()
    if (q) {
      const name = source?.source_name || ''
      const type = source?.source_type || ''
      const id = backup.backup_id || ''
      if (!name.toLowerCase().includes(q) && !type.toLowerCase().includes(q) && !id.includes(q)) return false
    }
    if (statusFilter !== STATUS_ALL) {
      const s = source ? source.status : backup.status
      if (s !== statusFilter) return false
    }
    if (typeFilter !== STATUS_ALL && source?.source_type !== typeFilter) return false
    if (quickFilter === STATUS_RESTORABLE) {
      if (!source || !RESTORABLE_TYPES.includes(source.source_type)) return false
      if (source.status !== 'completed') return false
    }
    return true
  })

  // Group by source name for display
  const grouped = {}
  for (const row of filtered) {
    const key = row.source?.source_name || row.backup.backup_id
    if (!grouped[key]) grouped[key] = { sourceName: key, sourceType: row.source?.source_type || 'unknown', rows: [] }
    grouped[key].rows.push(row)
  }
  const groups = Object.values(grouped)

  // ── Restore ────────────────────────────────────────────────────────────────
  const openRestoreModal = async (sourceId, sourceType) => {
    setRestoreModal({ sourceId, sourceType })
    setRestoreLoading(true)
    setRestoreStatus(null)
    setRestoreResult(null)
    setUseManualConnection(false)
    setRestoreForm({ backup_path: '', profile: '', target_connection_string: '', target_db_password: '', restore_storage: false, target_service_role_key: '' })

    try {
      const [restoresRes, credsRes] = await Promise.all([
        restoreAPI.getAvailable(sourceId),
        settingsAPI.getCredentials().catch(() => ({ data: {} })),
      ])
      const backupList = restoresRes.data.backups || []
      const profiles = credsRes.data?.supabase?.profiles || []
      setRestoreBackups(backupList)
      setSupabaseProfiles(profiles)
      setRestoreForm(prev => ({
        ...prev,
        backup_path: backupList[0]?.path || '',
        profile: profiles[0]?.profile || '',
      }))
    } catch (_error) {
      setRestoreBackups([])
    }
    setRestoreLoading(false)
  }

  const handleRestore = async () => {
    setConfirmRestore(false)
    setRestoreStatus('starting')
    try {
      const res = await restoreAPI.start(restoreForm)
      const restoreId = res.data.restore_id
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

  // ── Helpers ────────────────────────────────────────────────────────────────
  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B'
    const k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i]
  }

  const formatDuration = (s) => {
    if (!s) return '—'
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
    if (h > 0) return `${h}h ${m}m`
    if (m > 0) return `${m}m ${sec}s`
    return `${sec}s`
  }

  const statusIcon = (status, size = 'w-4 h-4') => {
    switch (status) {
      case 'completed': return <CheckCircle className={clsx(size, 'text-green-600')} />
      case 'failed':    return <XCircle className={clsx(size, 'text-red-600')} />
      case 'partial':   return <AlertCircle className={clsx(size, 'text-yellow-600')} />
      default:          return <Clock className={clsx(size, 'text-blue-600')} />
    }
  }

  const statusBadge = (status) => ({
    completed: 'badge-success', running: 'badge-info', failed: 'badge-error', partial: 'badge-warning',
  }[status] || 'badge-info')

  const typeIcon = (type) => {
    if (type === 'supabase') return <Database className="w-4 h-4 text-emerald-600" />
    return <HardDrive className="w-4 h-4 text-gray-400" />
  }

  const restorableCount = rows.filter(r => r.source && RESTORABLE_TYPES.includes(r.source.source_type) && r.source.status === 'completed').length

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="page-shell">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900">{t('backups.title')}</h1>
          <p className="text-sm text-gray-500 mt-1">{t('backups.subtitle')}</p>
        </div>
        <button onClick={loadBackups} className="btn btn-secondary w-full sm:w-auto">
          <RefreshCw className="w-4 h-4" />
          {t('common.refresh')}
        </button>
      </div>

      {/* Quick Filters */}
      <div className="flex gap-2 overflow-x-auto pb-1 sm:flex-wrap">
        <button
          onClick={() => setQuickFilter(null)}
          className={clsx('inline-flex min-h-9 shrink-0 items-center rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
            !quickFilter ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          )}
        >
          {t('backups.filterAll')} <span className="ml-1 opacity-70">{rows.length}</span>
        </button>
        <button
          onClick={() => setQuickFilter(STATUS_RESTORABLE)}
          className={clsx('inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
            quickFilter === STATUS_RESTORABLE ? 'bg-emerald-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          )}
        >
          <RotateCcw className="w-3.5 h-3.5" />
          {t('backups.filterRestorable')} <span className="ml-1 opacity-70">{restorableCount}</span>
        </button>
      </div>

      {/* Search + Filters */}
      <div className="card p-4 space-y-3">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1 min-w-0">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              className="input pl-9"
              placeholder={t('backups.searchPlaceholder')}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-gray-400 hover:text-gray-600" aria-label={t('common.clear')}>
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          <select
            className="input sm:w-40"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
          >
            <option value={STATUS_ALL}>{t('backups.allStatuses')}</option>
            <option value="completed">{t('dashboard.status.completed')}</option>
            <option value="failed">{t('dashboard.status.failed')}</option>
            <option value="partial">{t('dashboard.status.partial')}</option>
          </select>

          <select
            className="input sm:w-40"
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}
          >
            <option value={STATUS_ALL}>{t('backups.allTypes')}</option>
            {sourceTypes.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>

        {(search || statusFilter !== STATUS_ALL || typeFilter !== STATUS_ALL || quickFilter) && (
          <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
            <SlidersHorizontal className="w-4 h-4" />
            <span>{filtered.length} {t('backups.resultsOf')} {rows.length}</span>
            <button
              onClick={() => { setSearch(''); setStatusFilter(STATUS_ALL); setTypeFilter(STATUS_ALL); setQuickFilter(null) }}
              className="text-primary-600 hover:underline"
            >
              {t('backups.resetFilters')}
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : groups.length === 0 ? (
        <div className="card text-center py-14">
          <Archive className="w-14 h-14 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900">{t('backups.noResults')}</h3>
          <p className="text-sm text-gray-500 mt-1">{t('backups.noResultsHint')}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map(group => (
            <div key={group.sourceName} className="card overflow-hidden p-0">
              {/* Group Header */}
              <div className="flex flex-wrap items-center gap-3 border-b border-gray-100 bg-gray-50 px-4 py-3 md:px-5">
                {typeIcon(group.sourceType)}
                <span className="min-w-0 flex-1 break-words font-semibold text-gray-900">{group.sourceName}</span>
                <span className="shrink-0 text-xs text-gray-400 bg-gray-200 rounded-full px-2 py-0.5">{group.sourceType}</span>
                <span className="w-full text-xs text-gray-400 sm:ml-auto sm:w-auto">{group.rows.length} {t('backups.entries')}</span>
              </div>

              {/* Rows */}
              <div className="divide-y divide-gray-100">
                {group.rows.map(({ backup, source }) => {
                  const status = source ? source.status : backup.status
                  const logKey = source ? `${backup.backup_id}-${source.source_id}` : backup.backup_id
                  const isRestorable = source && RESTORABLE_TYPES.includes(source.source_type) && source.status === 'completed'

                  return (
                    <div key={logKey} className="px-4 py-3 md:px-5">
                      <div className="grid gap-3 md:grid-cols-[auto_minmax(8rem,12rem)_1fr_auto] md:items-center">
                        {statusIcon(status)}

                        {/* Date */}
                        <div className="flex min-w-0 items-center gap-1.5 text-sm text-gray-700">
                          <Calendar className="w-3.5 h-3.5 text-gray-400" />
                          <span className="truncate" title={format(new Date(backup.started_at), 'dd.MM.yyyy HH:mm:ss')}>
                            {formatDistanceToNow(new Date(backup.started_at), { addSuffix: true })}
                          </span>
                        </div>

                        {/* Stats */}
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
                          {source ? (
                            <>
                              <span>{source.files_synced ?? '—'} {t('backups.files')}</span>
                              <span>{formatBytes(source.size_synced)}</span>
                            </>
                          ) : (
                            <>
                              <span>{backup.sources_count} {t('backups.sourcesCount')}</span>
                              <span>{formatBytes(backup.total_size)}</span>
                              <span>{formatDuration(backup.duration)}</span>
                            </>
                          )}
                        </div>

                        {/* Badge + Actions */}
                        <div className="mobile-action-row">
                          <span className={clsx('badge text-xs', statusBadge(status))}>
                            {t(`dashboard.status.${status}`)}
                          </span>

                          {isRestorable && (
                            <button
                              onClick={() => openRestoreModal(source.source_id, source.source_type)}
                              className="btn min-h-9 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 hover:text-emerald-900"
                            >
                              <RotateCcw className="w-3 h-3" />
                              {t('restore.action')}
                            </button>
                          )}

                          {source && source.status === 'completed' && (
                            <button
                              onClick={() => openDownloadModal(source.source_id, source.source_name)}
                              className="btn min-h-9 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100 hover:text-blue-900"
                            >
                              <Download className="w-3 h-3" />
                              {t('backups.download')}
                            </button>
                          )}

                          {(source?.logs || source?.error_message || backup.error_message) && (
                            <button
                              onClick={() => setExpandedLogs(prev => ({ ...prev, [logKey]: !prev[logKey] }))}
                              className="btn min-h-9 px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-100 hover:text-gray-700"
                            >
                              <FileText className="w-3.5 h-3.5" />
                              {expandedLogs[logKey] ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Log drawer */}
                      {expandedLogs[logKey] && (
                        <div className="mt-3 md:ml-7">
                          {(source?.error_message || backup.error_message) && (
                            <div className="mb-2 overflow-x-auto rounded border border-red-200 bg-red-50 p-2 font-mono text-xs text-red-700 whitespace-pre-wrap">
                              {source?.error_message || backup.error_message}
                            </div>
                          )}
                          {source?.logs ? (
                            <pre className="max-h-48 overflow-auto rounded border bg-gray-50 p-2 font-mono text-xs text-gray-600 whitespace-pre-wrap">
                              {source.logs}
                            </pre>
                          ) : (
                            <p className="text-xs text-gray-400 italic">{t('restore.noLogs')}</p>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > limit && (
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0} className="btn btn-secondary disabled:opacity-50">
            {t('common.previous')}
          </button>
          <span className="text-sm text-gray-600">{t('history.page', { current: page + 1, total: Math.ceil(total / limit) })}</span>
          <button onClick={() => setPage(p => p + 1)} disabled={(page + 1) * limit >= total} className="btn btn-secondary disabled:opacity-50">
            {t('common.next')}
          </button>
        </div>
      )}

      {/* ── Download Modal ────────────────────────────────────────────────── */}
      {downloadModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="fixed inset-0 bg-black/50" onClick={() => setDownloadModal(null)} />
          <div className="modal-stage">
            <div className="modal-panel max-w-md">
              <div className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-200 bg-white px-4 py-4 md:px-6">
                <h2 className="flex min-w-0 items-center gap-2 text-lg font-bold text-gray-900">
                  <Download className="w-5 h-5" />
                  <span className="truncate">{downloadModal.sourceName}</span>
                </h2>
                <button onClick={() => setDownloadModal(null)} className="icon-btn shrink-0 hover:bg-gray-100" aria-label={t('common.close')}>
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-4 md:p-6">
                {downloadLoading ? (
                  <div className="flex items-center gap-2 text-gray-500 py-4 justify-center">
                    <Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}
                  </div>
                ) : downloadFiles.length === 0 ? (
                  <p className="text-sm text-gray-500 text-center py-4">{t('backups.noDownloadFiles')}</p>
                ) : (
                  <div className="space-y-2">
                    {downloadFiles.map(file => (
                      <div key={file.filename} className="flex flex-col gap-3 rounded-lg bg-gray-50 p-3 sm:flex-row sm:items-center">
                        <FileText className="w-4 h-4 text-gray-400 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="break-words text-sm font-medium text-gray-900">{file.filename}</p>
                          <p className="text-xs text-gray-400 break-words">
                            {formatBytes(file.size)} · {new Date(file.modified).toLocaleDateString()}
                            {file.type === 'directory' && ' · als .tar.gz'}
                          </p>
                        </div>
                        <button
                          onClick={() => triggerDownload(downloadModal.sourceId, file.filename)}
                          className="btn btn-secondary min-h-10 w-full shrink-0 px-3 py-1.5 text-xs sm:w-auto"
                        >
                          <Download className="w-3.5 h-3.5" />
                          {t('backups.download')}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Restore Modal ─────────────────────────────────────────────────── */}
      {restoreModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="fixed inset-0 bg-black/50" onClick={() => !restoreStatus && setRestoreModal(null)} />
          <div className="modal-stage">
            <div className="modal-panel max-w-lg">
              <div className="sticky top-0 z-10 bg-white border-b border-gray-200 px-4 md:px-6 py-4 flex items-center justify-between rounded-t-2xl sm:rounded-t-xl">
                <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2 min-w-0">
                  <RotateCcw className="w-5 h-5" /> {t('restore.title')}
                </h2>
                {!restoreStatus && (
                  <button onClick={() => setRestoreModal(null)} className="icon-btn hover:bg-gray-100" aria-label={t('common.close')}>
                    <X className="w-5 h-5" />
                  </button>
                )}
              </div>

              <div className="p-4 md:p-6 space-y-4">
                {/* Status display */}
                {restoreStatus && (
                  <div className={clsx('p-4 rounded-lg border',
                    restoreStatus === 'running' || restoreStatus === 'starting' ? 'bg-blue-50 border-blue-200' :
                    restoreStatus === 'completed' ? 'bg-green-50 border-green-200' :
                    restoreStatus === 'partial' ? 'bg-yellow-50 border-yellow-200' :
                    'bg-red-50 border-red-200'
                  )}>
                    <div className="flex items-center gap-3">
                      {(restoreStatus === 'running' || restoreStatus === 'starting') && <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />}
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
                        {restoreResult.errors.map((err, i) => <p key={i} className="text-xs text-red-700">{err}</p>)}
                      </div>
                    )}
                    {restoreResult?.error && <p className="mt-2 text-sm text-red-700">{restoreResult.error}</p>}
                    {restoreResult?.logs && (
                      <pre className="mt-3 text-xs text-gray-600 font-mono whitespace-pre-wrap max-h-48 overflow-y-auto bg-white p-2 rounded border">
                        {restoreResult.logs}
                      </pre>
                    )}
                    {['completed', 'partial', 'failed'].includes(restoreStatus) && (
                      <button onClick={() => { setRestoreModal(null); setRestoreStatus(null); setRestoreResult(null) }} className="mt-3 btn btn-secondary text-sm">
                        {t('common.close')}
                      </button>
                    )}
                  </div>
                )}

                {/* Form */}
                {!restoreStatus && (
                  <>
                    <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                      <p className="text-sm text-amber-800">
                        {t('restore.safetyWarning')}
                      </p>
                    </div>

                    {/* Backup selection */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">{t('restore.selectBackup')}</label>
                      {restoreLoading ? (
                        <div className="flex items-center gap-2 text-gray-500"><Loader2 className="w-4 h-4 animate-spin" /> {t('restore.loadingBackups')}</div>
                      ) : restoreBackups.length === 0 ? (
                        <p className="text-sm text-gray-500">{t('restore.noBackups')}</p>
                      ) : (
                        <select className="input" value={restoreForm.backup_path} onChange={e => setRestoreForm(p => ({ ...p, backup_path: e.target.value }))}>
                          {restoreBackups.map(b => (
                            <option key={b.path} value={b.path}>{b.filename} ({formatBytes(b.size)}) — {new Date(b.created).toLocaleString()}</option>
                          ))}
                        </select>
                      )}
                    </div>

                    {/* Profile / Manual */}
                    {!useManualConnection ? (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">{t('restore.targetProfile')}</label>
                        {supabaseProfiles.length === 0 ? (
                          <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                            <p className="text-sm text-amber-800">{t('restore.noProfile')}</p>
                          </div>
                        ) : (
                          <>
                            <select className="input" value={restoreForm.profile} onChange={e => setRestoreForm(p => ({ ...p, profile: e.target.value }))}>
                              {supabaseProfiles.map(p => <option key={p.profile} value={p.profile}>{p.profile}</option>)}
                            </select>
                            <p className="text-xs text-gray-500 mt-1">{t('restore.profileHint')}</p>
                          </>
                        )}
                        <button type="button" onClick={() => setUseManualConnection(true)} className="mt-2 text-xs text-blue-600 hover:text-blue-800 underline">
                          {t('restore.manualConnection')}
                        </button>
                      </div>
                    ) : (
                      <>
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <label className="block text-sm font-medium text-gray-700">{t('restore.connectionString')}</label>
                            <button type="button" onClick={() => setUseManualConnection(false)} className="text-xs text-blue-600 hover:text-blue-800 underline">
                              {t('restore.useProfile')}
                            </button>
                          </div>
                          <input type="text" className="input font-mono text-sm" value={restoreForm.target_connection_string}
                            onChange={e => setRestoreForm(p => ({ ...p, target_connection_string: e.target.value }))}
                            placeholder="postgresql://postgres.xxxxx:[YOUR-PASSWORD]@..." />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-2">{t('restore.dbPassword')}</label>
                          <div className="relative">
                            <input type={showRestorePassword ? 'text' : 'password'} className="input pr-10"
                              value={restoreForm.target_db_password} onChange={e => setRestoreForm(p => ({ ...p, target_db_password: e.target.value }))}
                              placeholder={t('restore.dbPasswordPlaceholder')} />
                            <button type="button" onClick={() => setShowRestorePassword(v => !v)} className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500">
                              {showRestorePassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                            </button>
                          </div>
                        </div>
                      </>
                    )}

                    {/* Storage toggle */}
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                        checked={restoreForm.restore_storage} onChange={e => setRestoreForm(p => ({ ...p, restore_storage: e.target.checked }))} />
                      <span className="text-sm text-gray-700">{t('restore.storage')}</span>
                    </label>

                    {/* Service key — only manual mode */}
                    {restoreForm.restore_storage && useManualConnection && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">{t('restore.serviceRoleKey')}</label>
                        <div className="relative">
                          <input type={showServiceKey ? 'text' : 'password'} className="input pr-10"
                            value={restoreForm.target_service_role_key} onChange={e => setRestoreForm(p => ({ ...p, target_service_role_key: e.target.value }))}
                            placeholder="eyJ..." />
                          <button type="button" onClick={() => setShowServiceKey(v => !v)} className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500">
                            {showServiceKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row">
                      <button onClick={() => setRestoreModal(null)} className="btn btn-secondary flex-1">{t('common.cancel')}</button>
                      <button
                        onClick={() => setConfirmRestore(true)}
                        disabled={!restoreForm.backup_path || (useManualConnection ? !restoreForm.target_connection_string : !restoreForm.profile)}
                        className="btn btn-primary flex-1 disabled:opacity-50"
                      >
                        <RotateCcw className="w-4 h-4 mr-2" /> {t('restore.start')}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

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
