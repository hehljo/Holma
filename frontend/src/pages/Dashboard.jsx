import { useState, useEffect, useCallback } from 'react'
import { Play, Clock, CheckCircle, XCircle, HardDrive, Database, ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import { backupAPI, sourcesAPI } from '../services/api'
import clsx from 'clsx'
import { useTranslation } from 'react-i18next'
import { StatsGridSkeleton, CardGridSkeleton, TableRowSkeleton } from '../components/Skeleton'

export default function Dashboard() {
  const { t } = useTranslation()
  const [stats, setStats] = useState(null)
  const [sources, setSources] = useState([])
  const [isStarting, setIsStarting] = useState(false)
  const [recentBackups, setRecentBackups] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [runningBackup, setRunningBackup] = useState(null) // full backup object with sources
  const [expandedLiveLogs, setExpandedLiveLogs] = useState({})
  const loadData = useCallback(async () => {
    try {
      const [statsRes, sourcesRes, historyRes] = await Promise.all([
        backupAPI.getStats(),
        sourcesAPI.getAll(),
        backupAPI.getHistory(5, 0)
      ])

      setStats(statsRes.data)
      setSources(sourcesRes.data.sources)
      const backups = historyRes.data.backups || []
      setRecentBackups(backups)

      // Track actively running backup with live source details
      const active = backups.find(b => b.status === 'running')
      if (active) {
        try {
          const statusRes = await backupAPI.getStatus(active.backup_id)
          setRunningBackup(statusRes.data)
        } catch (_) {
          setRunningBackup(active)
        }
      } else {
        setRunningBackup(null)
      }

      setIsLoading(false)
    } catch (error) {
      console.error('Error loading data:', error)
      setIsLoading(false)
    }
  }, [])

  const hasRunningBackup = Boolean(runningBackup)
  useEffect(() => {
    loadData()
    const interval = window.setInterval(
      loadData,
      hasRunningBackup ? 3000 : 10000,
    )
    return () => window.clearInterval(interval)
  }, [hasRunningBackup, loadData])

  const handleStartBackup = async () => {
    setIsStarting(true)
    try {
      await backupAPI.start({ parallel: 2, notify: true })
      setTimeout(loadData, 2000) // Reload after 2 seconds
    } catch (error) {
      console.error('Error starting backup:', error)
      alert(t('common.error'))
    } finally {
      setIsStarting(false)
    }
  }

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
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

  if (isLoading) {
    return (
      <div className="page-shell">
        {/* Header Skeleton */}
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="space-y-2">
            <div className="h-8 w-48 bg-gray-200 rounded animate-pulse"></div>
            <div className="h-4 w-64 bg-gray-200 rounded animate-pulse"></div>
          </div>
          <div className="h-11 w-full md:w-40 bg-gray-200 rounded-lg animate-pulse"></div>
        </div>

        {/* Stats Skeleton */}
        <StatsGridSkeleton count={4} />

        {/* Sources Grid Skeleton */}
        <div className="space-y-3">
          <div className="h-6 w-32 bg-gray-200 rounded animate-pulse"></div>
          <CardGridSkeleton count={2} />
        </div>

        {/* Recent Backups Skeleton */}
        <div className="space-y-3">
          <div className="h-6 w-40 bg-gray-200 rounded animate-pulse"></div>
          <div className="card">
            {[...Array(3)].map((_, i) => (
              <TableRowSkeleton key={i} />
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="page-shell">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900">{t('dashboard.title')}</h1>
          <p className="text-sm md:text-base text-gray-600 mt-1">{t('dashboard.subtitle')}</p>
        </div>
        <button
          onClick={handleStartBackup}
          disabled={isStarting || stats?.running > 0}
          className={clsx(
            'btn btn-primary flex items-center justify-center gap-2 w-full md:w-auto',
            (isStarting || stats?.running > 0) && 'opacity-50 cursor-not-allowed'
          )}
        >
          <Play className="w-5 h-5" />
          <span className="truncate">{isStarting ? t('common.loading') : t('dashboard.startBackup')}</span>
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        <div className="card">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs md:text-sm text-gray-600 truncate">{t('dashboard.stats.totalBackups')}</p>
              <p className="text-2xl md:text-3xl font-bold text-gray-900 mt-1 md:mt-2">
                {stats?.total_backups || 0}
              </p>
            </div>
            <div className="p-2 md:p-3 bg-blue-100 rounded-lg shrink-0">
              <HardDrive className="w-6 h-6 md:w-8 md:h-8 text-blue-600" />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs md:text-sm text-gray-600 truncate">{t('dashboard.stats.successful')}</p>
              <p className="text-2xl md:text-3xl font-bold text-green-600 mt-1 md:mt-2">
                {stats?.successful || 0}
              </p>
            </div>
            <div className="p-2 md:p-3 bg-green-100 rounded-lg shrink-0">
              <CheckCircle className="w-6 h-6 md:w-8 md:h-8 text-green-600" />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs md:text-sm text-gray-600 truncate">{t('dashboard.stats.failed')}</p>
              <p className="text-2xl md:text-3xl font-bold text-red-600 mt-1 md:mt-2">
                {stats?.failed || 0}
              </p>
            </div>
            <div className="p-2 md:p-3 bg-red-100 rounded-lg shrink-0">
              <XCircle className="w-6 h-6 md:w-8 md:h-8 text-red-600" />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs md:text-sm text-gray-600 truncate">{t('dashboard.stats.totalSize')}</p>
              <p className="text-2xl md:text-3xl font-bold text-gray-900 mt-1 md:mt-2 truncate">
                {formatBytes(stats?.total_size_bytes || 0)}
              </p>
            </div>
            <div className="p-2 md:p-3 bg-purple-100 rounded-lg shrink-0">
              <Database className="w-6 h-6 md:w-8 md:h-8 text-purple-600" />
            </div>
          </div>
        </div>
      </div>

      {/* Live Backup Panel */}
      {runningBackup && (
        <div className="card border-2 border-blue-200 bg-blue-50">
          <div className="flex items-center gap-3 mb-4">
            <Loader2 className="w-5 h-5 text-blue-600 animate-spin shrink-0" />
            <div className="flex-1 min-w-0">
              <h2 className="text-base md:text-lg font-bold text-blue-900">{t('dashboard.backupRunning')}</h2>
              <p className="text-xs text-blue-600">
                {runningBackup.sources?.filter(s => s.status === 'completed').length ?? 0} / {runningBackup.sources_count ?? runningBackup.sources?.length ?? '?'} {t('dashboard.sourcesCompleted')}
              </p>
            </div>
          </div>

          <div className="space-y-2">
            {(runningBackup.sources || []).map(source => (
              <div key={source.source_id} className="bg-white rounded-lg overflow-hidden border border-blue-100">
                <div className="flex items-center gap-3 px-3 py-2">
                  {source.status === 'running' && <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin shrink-0" />}
                  {source.status === 'completed' && <CheckCircle className="w-3.5 h-3.5 text-green-500 shrink-0" />}
                  {source.status === 'failed' && <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />}
                  {!['running','completed','failed'].includes(source.status) && <Clock className="w-3.5 h-3.5 text-gray-400 shrink-0" />}

                  <span className="text-sm font-medium text-gray-900 flex-1 truncate">{source.source_name}</span>
                  <span className="text-xs text-gray-400">{source.source_type}</span>

                  {source.logs && (
                    <button
                      onClick={() => setExpandedLiveLogs(prev => ({ ...prev, [source.source_id]: !prev[source.source_id] }))}
                      className="flex items-center gap-1 text-xs text-blue-500 hover:text-blue-700 ml-2"
                    >
                      Logs {expandedLiveLogs[source.source_id] ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    </button>
                  )}
                </div>

                {expandedLiveLogs[source.source_id] && source.logs && (
                  <div className="border-t border-blue-100 px-3 py-2 bg-gray-50">
                    <pre className="text-xs text-gray-600 font-mono whitespace-pre-wrap max-h-48 overflow-y-auto">
                      {source.logs}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sources Overview */}
      <div className="card">
        <h2 className="text-lg md:text-xl font-bold text-gray-900 mb-3 md:mb-4">{t('dashboard.backupSources')}</h2>
        <div className="space-y-2 md:space-y-3">
          {sources.filter(s => s.enabled).map((source) => (
            <div key={source.id} className="flex items-center justify-between p-3 md:p-4 bg-gray-50 rounded-lg gap-2">
              <div className="flex items-center gap-2 md:gap-3 min-w-0 flex-1">
                <div className={clsx(
                  'w-2.5 h-2.5 md:w-3 md:h-3 rounded-full shrink-0',
                  source.enabled ? 'bg-green-500' : 'bg-gray-300'
                )}></div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-sm md:text-base text-gray-900 truncate">{source.name}</p>
                  <p className="text-xs md:text-sm text-gray-600">{source.type.toUpperCase()}</p>
                </div>
              </div>
              <span className="badge badge-success shrink-0 text-xs md:text-sm">{t('dashboard.active')}</span>
            </div>
          ))}
          {sources.filter(s => s.enabled).length === 0 && (
            <p className="text-sm md:text-base text-gray-500 text-center py-4">{t('dashboard.noSources')}</p>
          )}
        </div>
      </div>

      {/* Recent Backups */}
      <div className="card">
        <h2 className="text-lg md:text-xl font-bold text-gray-900 mb-3 md:mb-4">{t('dashboard.recentBackups')}</h2>
        <div className="space-y-2 md:space-y-3">
          {recentBackups.map((backup) => (
            <div key={backup.backup_id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between p-3 md:p-4 bg-gray-50 rounded-lg gap-3">
              <div className="flex items-start gap-2 md:gap-4 min-w-0 flex-1">
                <Clock className="w-4 h-4 md:w-5 md:h-5 text-gray-400 shrink-0 mt-0.5" />
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-sm md:text-base text-gray-900 truncate">
                    {new Date(backup.started_at).toLocaleString()}
                  </p>
                  <p className="text-xs md:text-sm text-gray-600 truncate">
                    {backup.sources_count} sources • {formatBytes(backup.total_size)}
                  </p>
                </div>
              </div>
              <span className={clsx('badge self-start sm:self-center shrink-0 text-xs md:text-sm', getStatusBadge(backup.status))}>
                {t(`dashboard.status.${backup.status}`)}
              </span>
            </div>
          ))}
          {recentBackups.length === 0 && (
            <p className="text-sm md:text-base text-gray-500 text-center py-4">{t('dashboard.noBackups')}</p>
          )}
        </div>
      </div>
    </div>
  )
}
