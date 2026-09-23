import { useState, useEffect, useCallback } from 'react'
import { GitBranch, Lock, Unlock, RefreshCw, Search, AlertCircle } from 'lucide-react'
import { sourcesAPI } from '../services/api'
import clsx from 'clsx'
import PropTypes from 'prop-types'
import { useTranslation } from 'react-i18next'

/**
 * GitHub Repository Selector Component
 * Fetches repos via discovery API and lets the user toggle between
 * "all" (discovery_mode) or manual selection.
 *
 * Props:
 *   discoveryMode: 'all' | 'manual'
 *   selectedRepos: string[] (full_name list for manual mode)
 *   excludeRepos: string[] (full_name list for all mode)
 *   onDiscoveryModeChange: (mode) => void
 *   onSelectedReposChange: (repos) => void
 *   onExcludeChange: (excludes) => void
 */
export default function GitHubRepoSelector({
  discoveryMode = 'manual',
  selectedRepos = [],
  excludeRepos = [],
  onDiscoveryModeChange,
  onSelectedReposChange,
  onExcludeChange,
}) {
  const { t } = useTranslation()
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')

  const fetchRepos = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await sourcesAPI.discoverGitHub()
      setRepos(response.data.repos || [])
    } catch (err) {
      const msg = err.response?.data?.error || t('githubSelector.loadError')
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    fetchRepos()
  }, [fetchRepos])

  const filteredRepos = repos.filter(repo =>
    repo.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (repo.description && repo.description.toLowerCase().includes(searchQuery.toLowerCase()))
  )

  const isRepoSelected = (fullName) => {
    if (discoveryMode === 'all') {
      return !excludeRepos.includes(fullName)
    }
    return selectedRepos.includes(fullName)
  }

  const toggleRepo = (fullName) => {
    if (discoveryMode === 'all') {
      // In "all" mode, toggling OFF adds to exclude list
      if (excludeRepos.includes(fullName)) {
        onExcludeChange(excludeRepos.filter(r => r !== fullName))
      } else {
        onExcludeChange([...excludeRepos, fullName])
      }
    } else {
      // In "manual" mode, toggling adds/removes from selected list
      if (selectedRepos.includes(fullName)) {
        onSelectedReposChange(selectedRepos.filter(r => r !== fullName))
      } else {
        onSelectedReposChange([...selectedRepos, fullName])
      }
    }
  }

  const formatSize = (sizeKB) => {
    if (sizeKB < 1024) return `${sizeKB} KB`
    if (sizeKB < 1024 * 1024) return `${(sizeKB / 1024).toFixed(1)} MB`
    return `${(sizeKB / (1024 * 1024)).toFixed(1)} GB`
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    return date.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    })
  }

  const selectedCount = discoveryMode === 'all'
    ? repos.length - excludeRepos.length
    : selectedRepos.length

  return (
    <div className="space-y-4">
      {/* Discovery Mode Toggle */}
      <div className="flex items-center gap-4">
        <label className="block text-sm font-medium text-gray-700">
          {t('githubSelector.mode')}
        </label>
        <div className="flex rounded-lg overflow-hidden border border-gray-300">
          <button
            type="button"
            className={clsx(
              'px-4 py-2 text-sm font-medium transition-colors',
              discoveryMode === 'all'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            )}
            onClick={() => onDiscoveryModeChange('all')}
          >
            {t('githubSelector.all')}
          </button>
          <button
            type="button"
            className={clsx(
              'px-4 py-2 text-sm font-medium transition-colors',
              discoveryMode === 'manual'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            )}
            onClick={() => onDiscoveryModeChange('manual')}
          >
            {t('githubSelector.manual')}
          </button>
        </div>
      </div>

      {discoveryMode === 'all' && (
        <p className="text-sm text-gray-500">
          {t('githubSelector.allHint')}
        </p>
      )}

      {/* Search & Refresh */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            className="input pl-9"
            placeholder={t('githubSelector.search')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <button
          type="button"
          className="btn btn-secondary flex items-center gap-2"
          onClick={fetchRepos}
          disabled={loading}
        >
          <RefreshCw className={clsx('w-4 h-4', loading && 'animate-spin')} />
          {t('githubSelector.refresh')}
        </button>
      </div>

      {/* Status Bar */}
      <div className="text-sm text-gray-500">
        {loading
          ? t('githubSelector.loading')
          : t('githubSelector.selected', { selected: selectedCount, total: repos.length })}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Repository List */}
      {!loading && !error && (
        <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-100">
          {filteredRepos.map((repo) => (
            <label
              key={repo.full_name}
              className={clsx(
                'flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors',
                isRepoSelected(repo.full_name)
                  ? 'bg-blue-50 hover:bg-blue-100'
                  : 'bg-white hover:bg-gray-50'
              )}
            >
              <input
                type="checkbox"
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                checked={isRepoSelected(repo.full_name)}
                onChange={() => toggleRepo(repo.full_name)}
              />

              <GitBranch className="w-4 h-4 text-gray-400 flex-shrink-0" />

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm text-gray-900 truncate">
                    {repo.full_name}
                  </span>
                  {repo.private ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                      <Lock className="w-3 h-3" />
                      {t('githubSelector.private')}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      <Unlock className="w-3 h-3" />
                      {t('githubSelector.public')}
                    </span>
                  )}
                  {repo.fork && (
                    <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                      {t('githubSelector.fork')}
                    </span>
                  )}
                  {repo.archived && (
                    <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700">
                      {t('githubSelector.archived')}
                    </span>
                  )}
                </div>
                {repo.description && (
                  <p className="text-xs text-gray-500 truncate mt-0.5">
                    {repo.description}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-4 text-xs text-gray-400 flex-shrink-0">
                <span>{formatSize(repo.size)}</span>
                <span>{formatDate(repo.updated_at)}</span>
              </div>
            </label>
          ))}

          {filteredRepos.length === 0 && (
            <div className="px-4 py-8 text-center text-gray-500 text-sm">
              {searchQuery ? t('githubSelector.noMatch') : t('githubSelector.empty')}
            </div>
          )}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-14 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
      )}
    </div>
  )
}

GitHubRepoSelector.propTypes = {
  discoveryMode: PropTypes.oneOf(['all', 'manual']),
  selectedRepos: PropTypes.arrayOf(PropTypes.string),
  excludeRepos: PropTypes.arrayOf(PropTypes.string),
  onDiscoveryModeChange: PropTypes.func.isRequired,
  onSelectedReposChange: PropTypes.func.isRequired,
  onExcludeChange: PropTypes.func.isRequired,
}
