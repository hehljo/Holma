import { useState, useEffect, useRef, useCallback } from 'react'
import { FileText, RefreshCw, Trash2, Download, ArrowDown } from 'lucide-react'
import { settingsAPI } from '../services/api'
import { useTranslation } from 'react-i18next'
import toast from 'react-hot-toast'
import { BRAND } from '../brand'

export default function Logs() {
  const { t } = useTranslation()
  const [logs, setLogs] = useState('')
  const [lineCount, setLineCount] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [maxLines, setMaxLines] = useState(200)
  const [filter, setFilter] = useState('')
  const logRef = useRef(null)

  const loadLogs = useCallback(async () => {
    try {
      const response = await settingsAPI.getLogs(maxLines)
      setLogs(response.data.logs)
      setLineCount(response.data.lines)
      setIsLoading(false)
    } catch (error) {
      console.error('Error loading logs:', error)
      setIsLoading(false)
    }
  }, [maxLines])

  useEffect(() => {
    loadLogs()
  }, [loadLogs])

  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(loadLogs, 5000)
    return () => clearInterval(interval)
  }, [autoRefresh, loadLogs])

  const handleClear = async () => {
    if (!window.confirm(t('logs.confirmClear'))) return
    try {
      await settingsAPI.clearLogs()
      setLogs('')
      setLineCount(0)
      toast.success(t('logs.cleared'))
    } catch (_error) {
      toast.error(t('common.error'))
    }
  }

  const handleDownload = () => {
    const blob = new Blob([logs], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${BRAND.slug}_${new Date().toISOString().slice(0, 10)}.log`
    a.click()
    URL.revokeObjectURL(url)
  }

  const scrollToBottom = () => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }

  const filteredLogs = filter
    ? logs.split('\n').filter(line => line.toLowerCase().includes(filter.toLowerCase())).join('\n')
    : logs

  const getLineClass = (line) => {
    if (line.includes('ERROR')) return 'text-red-400'
    if (line.includes('WARNING')) return 'text-yellow-400'
    if (line.includes('INFO')) return 'text-green-400'
    if (line.includes('DEBUG')) return 'text-gray-500'
    return 'text-gray-300'
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900">{t('logs.title')}</h1>
          <p className="text-sm text-gray-600 mt-1">{t('logs.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <FileText className="w-4 h-4" />
          <span>{lineCount} {t('logs.lines')}</span>
        </div>
      </div>

      {/* Toolbar */}
      <div className="card p-3">
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Filter */}
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t('logs.filterPlaceholder')}
            className="input flex-1 text-sm"
          />

          {/* Lines selector */}
          <select
            value={maxLines}
            onChange={(e) => setMaxLines(Number(e.target.value))}
            className="input w-auto text-sm"
          >
            <option value={100}>100 {t('logs.lines')}</option>
            <option value={200}>200 {t('logs.lines')}</option>
            <option value={500}>500 {t('logs.lines')}</option>
            <option value={1000}>1000 {t('logs.lines')}</option>
          </select>

          {/* Action buttons */}
          <div className="grid grid-cols-5 gap-2 sm:flex sm:items-center">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`btn btn-secondary text-sm px-3 py-2 ${autoRefresh ? 'ring-2 ring-primary-500 bg-primary-50' : ''}`}
              title={t('logs.autoRefresh')}
            >
              <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={loadLogs}
              className="btn btn-secondary text-sm px-3 py-2"
              title={t('common.refresh')}
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={scrollToBottom}
              className="btn btn-secondary text-sm px-3 py-2"
              title={t('logs.scrollToBottom')}
            >
              <ArrowDown className="w-4 h-4" />
            </button>
            <button
              onClick={handleDownload}
              className="btn btn-secondary text-sm px-3 py-2"
              title={t('logs.download')}
            >
              <Download className="w-4 h-4" />
            </button>
            <button
              onClick={handleClear}
              className="btn btn-secondary text-sm px-3 py-2 text-red-600 hover:bg-red-50"
              title={t('logs.clear')}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Log Output */}
      <div className="card p-0 overflow-hidden">
        <pre
          ref={logRef}
          className="bg-gray-900 text-sm font-mono p-4 overflow-auto"
          style={{ maxHeight: 'calc(100vh - 320px)', minHeight: '400px' }}
        >
          {filteredLogs ? (
            filteredLogs.split('\n').map((line, i) => (
              <div key={i} className={`${getLineClass(line)} hover:bg-gray-800 px-1`}>
                {line}
              </div>
            ))
          ) : (
            <span className="text-gray-500 italic">{t('logs.empty')}</span>
          )}
        </pre>
      </div>
    </div>
  )
}
