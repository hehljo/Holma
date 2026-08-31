import { useState, useEffect, useRef } from 'react'
import { Plus, Edit2, Trash2, TestTube, Database, Play, Loader2 } from 'lucide-react'
import { sourcesAPI, backupAPI } from '../services/api'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { useTranslation } from 'react-i18next'
import SourceModal from '../components/SourceModal'
import ConfirmDialog from '../components/ConfirmDialog'
import { CardGridSkeleton } from '../components/Skeleton'

export default function Sources() {
  const { t } = useTranslation()
  const [sources, setSources] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingSource, setEditingSource] = useState(null)
  const [isSaving, setIsSaving] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState({ show: false, source: null })
  const [isDeleting, setIsDeleting] = useState(false)
  const [runningSources, setRunningSources] = useState([])
  const [startingSource, setStartingSource] = useState(null)
  const pollRef = useRef(null)

  useEffect(() => {
    loadSources()
    loadRunningSources()
    return () => clearTimeout(pollRef.current)
  }, [])

  // Poll while something is running so the spinner clears on its own; idle
  // pages stay quiet.
  useEffect(() => {
    clearTimeout(pollRef.current)
    if (runningSources.length === 0) return
    pollRef.current = setTimeout(loadRunningSources, 3000)
    return () => clearTimeout(pollRef.current)
  }, [runningSources])

  const loadRunningSources = async () => {
    try {
      const response = await backupAPI.getRunningSources()
      setRunningSources(response.data.source_ids || [])
    } catch (error) {
      console.error('Error loading running sources:', error)
    }
  }

  const loadSources = async () => {
    try {
      const response = await sourcesAPI.getAll()
      setSources(response.data.sources)
      setIsLoading(false)
    } catch (error) {
      console.error('Error loading sources:', error)
      toast.error('Failed to load sources')
      setIsLoading(false)
    }
  }

  const handleDeleteClick = (source) => {
    setDeleteConfirm({ show: true, source })
  }

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.source) return

    setIsDeleting(true)
    try {
      await sourcesAPI.delete(deleteConfirm.source.id)
      toast.success(`Source "${deleteConfirm.source.name}" deleted successfully`)
      setDeleteConfirm({ show: false, source: null })
      loadSources()
    } catch (error) {
      console.error('Error deleting source:', error)
      toast.error(error.response?.data?.error || 'Failed to delete source')
    } finally {
      setIsDeleting(false)
    }
  }

  const handleTest = async (sourceId) => {
    const loadingToast = toast.loading('Testing connection...')
    try {
      const response = await sourcesAPI.test(sourceId)
      toast.success(response.data.message || 'Connection test successful!', { id: loadingToast })
    } catch (error) {
      console.error('Error testing source:', error)
      toast.error(error.response?.data?.error || 'Connection test failed', { id: loadingToast })
    }
  }

  const handleBackupNow = async (source) => {
    setStartingSource(source.id)
    const loadingToast = toast.loading(t('sources.backupStarting', { name: source.name }))
    try {
      await backupAPI.start({ sources: [source.id], parallel: 1 })
      toast.success(t('sources.backupStarted', { name: source.name }), { id: loadingToast })
      setRunningSources((prev) => (prev.includes(source.id) ? prev : [...prev, source.id]))
    } catch (error) {
      console.error('Error starting backup:', error)
      // 409 means another run already has this source - not a failure the user
      // needs to act on, so say what is happening instead of "error".
      const message = error.response?.status === 409
        ? t('sources.backupAlreadyRunning', { name: source.name })
        : error.response?.data?.error || t('common.error')
      toast.error(message, { id: loadingToast })
      loadRunningSources()
    } finally {
      setStartingSource(null)
    }
  }

  const handleSave = async (sourceData) => {
    setIsSaving(true)
    const loadingToast = toast.loading(editingSource ? 'Updating source...' : 'Creating source...')
    try {
      if (editingSource) {
        await sourcesAPI.update(editingSource.id, sourceData)
        toast.success('Source updated successfully', { id: loadingToast })
      } else {
        await sourcesAPI.create(sourceData)
        toast.success('Source created successfully', { id: loadingToast })
      }
      setShowModal(false)
      setEditingSource(null)
      loadSources()
    } catch (error) {
      console.error('Error saving source:', error)
      toast.error(error.response?.data?.error || t('common.error'), { id: loadingToast })
    } finally {
      setIsSaving(false)
    }
  }

  const getTypeIcon = (type) => {
    return <Database className="w-5 h-5" />
  }

  if (isLoading) {
    return (
      <div className="page-shell">
        {/* Header Skeleton */}
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="space-y-2">
            <div className="h-8 w-48 bg-gray-200 rounded animate-pulse"></div>
            <div className="h-4 w-72 bg-gray-200 rounded animate-pulse"></div>
          </div>
          <div className="h-11 w-full md:w-44 bg-gray-200 rounded-lg animate-pulse"></div>
        </div>

        {/* Sources Grid Skeleton */}
        <CardGridSkeleton count={4} />
      </div>
    )
  }

  return (
    <div className="page-shell">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900">{t('sources.title')}</h1>
          <p className="text-sm md:text-base text-gray-600 mt-1">{t('sources.subtitle')}</p>
        </div>
        <button
          onClick={() => {
            setEditingSource(null)
            setShowModal(true)
          }}
          className="btn btn-primary flex items-center justify-center gap-2 w-full md:w-auto"
        >
          <Plus className="w-5 h-5" />
          {t('sources.addSource')}
        </button>
      </div>

      {/* Sources Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        {sources.map((source) => (
          <div key={source.id} className="card">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <div className="shrink-0 rounded-lg bg-primary-100 p-3">
                  {getTypeIcon(source.type)}
                </div>
                <div className="min-w-0">
                  <h3 className="break-words font-bold text-gray-900">{source.name}</h3>
                  <p className="truncate text-sm text-gray-600">{source.type.toUpperCase()}</p>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-2 sm:flex sm:items-center">
                {(() => {
                  const isRunning = runningSources.includes(source.id)
                  const isStarting = startingSource === source.id
                  const busy = isRunning || isStarting
                  // A disabled source is filtered out by the executor, so the
                  // button must not pretend it would do something.
                  const blocked = busy || !source.enabled
                  const label = !source.enabled
                    ? t('sources.backupNowDisabled')
                    : isRunning
                      ? t('sources.backupRunning')
                      : t('sources.backupNow')
                  return (
                    <button
                      onClick={() => handleBackupNow(source)}
                      disabled={blocked}
                      className={clsx(
                        'icon-btn',
                        blocked
                          ? 'text-gray-400 cursor-not-allowed'
                          : 'text-green-600 hover:bg-green-50'
                      )}
                      title={label}
                      aria-label={label}
                    >
                      {busy
                        ? <Loader2 className="w-5 h-5 animate-spin" />
                        : <Play className="w-5 h-5" />}
                    </button>
                  )
                })()}
                <button
                  onClick={() => handleTest(source.id)}
                  className="icon-btn text-blue-600 hover:bg-blue-50"
                  title={t('sources.testConnection')}
                  aria-label={t('sources.testConnection')}
                >
                  <TestTube className="w-5 h-5" />
                </button>
                <button
                  onClick={() => {
                    setEditingSource(source)
                    setShowModal(true)
                  }}
                  className="icon-btn text-gray-600 hover:bg-gray-100"
                  title={t('sources.edit')}
                  aria-label={t('sources.edit')}
                >
                  <Edit2 className="w-5 h-5" />
                </button>
                <button
                  onClick={() => handleDeleteClick(source)}
                  className="icon-btn text-red-600 hover:bg-red-50"
                  title={t('sources.delete')}
                  aria-label={t('sources.delete')}
                >
                  <Trash2 className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-gray-600">{t('sources.status')}</span>
                <span className={clsx(
                  'badge',
                  source.enabled ? 'badge-success' : 'badge-warning'
                )}>
                  {source.enabled ? t('sources.enabled') : t('sources.disabled')}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-gray-600">{t('sources.priority')}</span>
                <span className="font-medium">{source.priority}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {sources.length === 0 && (
        <div className="card text-center py-12">
          <Database className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-900 mb-2">{t('sources.noSources')}</h3>
          <p className="text-gray-600 mb-6">{t('sources.noSourcesHint')}</p>
          <button
            onClick={() => setShowModal(true)}
            className="btn btn-primary inline-flex items-center gap-2"
          >
            <Plus className="w-5 h-5" />
            {t('sources.addSource')}
          </button>
        </div>
      )}

      {/* Source Modal */}
      <SourceModal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false)
          setEditingSource(null)
        }}
        onSave={handleSave}
        editingSource={editingSource}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.show}
        onClose={() => setDeleteConfirm({ show: false, source: null })}
        onConfirm={handleDeleteConfirm}
        title="Delete Source?"
        message={`Are you sure you want to delete "${deleteConfirm.source?.name}"? This action cannot be undone.`}
        confirmText="Delete Source"
        confirmVariant="danger"
        isLoading={isDeleting}
      />

      {/* Keyboard Shortcuts Modal */}
    </div>
  )
}
