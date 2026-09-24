import { useState, useEffect } from 'react'
import {
  X, HardDrive, Cloud, Folder, Database, Eye, EyeOff,
  GitBranch, Server, Home, Package, Activity, Boxes, AlertCircle,
  Search, Zap, CheckCircle, Loader2
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import { sourcesAPI, settingsAPI } from '../services/api'
import GitHubRepoSelector from './GitHubRepoSelector'
import ScheduleFields from './ScheduleFields'
import { DEFAULT_SCHEDULE, describeSchedule } from './schedule'
import PropTypes from 'prop-types'
import { BRAND } from '../brand'

// Only source types supported by the standard container and this form.
const SOURCE_TYPES = [
  // Network Storage
  { value: 'nas', icon: HardDrive, category: 'network' },
  { value: 'rsync-ssh', icon: Server, category: 'network' },
  { value: 'webdav', icon: Cloud, category: 'network' },

  // Local Storage (1)
  { value: 'local', icon: Folder, category: 'local' },

  // Git Platforms (6)
  { value: 'github', icon: GitBranch, category: 'git' },
  { value: 'gitlab', icon: GitBranch, category: 'git' },
  { value: 'gitea', icon: GitBranch, category: 'git' },
  { value: 'forgejo', icon: GitBranch, category: 'git' },
  { value: 'bitbucket', icon: GitBranch, category: 'git' },
  { value: 'codeberg', icon: GitBranch, category: 'git' },

  // Databases
  { value: 'mysql', icon: Database, category: 'databases' },
  { value: 'postgresql', icon: Database, category: 'databases' },
  { value: 'redis', icon: Database, category: 'databases' },
  { value: 'sqlite', icon: Database, category: 'databases' },
  { value: 'couchdb', icon: Database, category: 'databases' },

  // Cloud Storage (10)
  { value: 'gdrive', icon: Cloud, category: 'cloud' },
  { value: 'onedrive', icon: Cloud, category: 'cloud' },
  { value: 'dropbox', icon: Cloud, category: 'cloud' },
  { value: 's3', icon: Cloud, category: 'cloud' },
  { value: 'b2', icon: Cloud, category: 'cloud' },
  { value: 'icloud', icon: Cloud, category: 'cloud' },
  { value: 'box', icon: Cloud, category: 'cloud' },
  { value: 'mega', icon: Cloud, category: 'cloud' },
  { value: 'pcloud', icon: Cloud, category: 'cloud' },
  { value: 'rclone', icon: Cloud, category: 'cloud' },

  // FTP/SFTP (3)
  { value: 'ftp', icon: Server, category: 'transfer' },
  { value: 'sftp', icon: Server, category: 'transfer' },

  // Docker (2)
  { value: 'docker-volume', icon: Package, category: 'docker' },
  { value: 'docker-image', icon: Boxes, category: 'docker' },

  // Read-only API configuration exports
  { value: 'homeassistant', icon: Home, category: 'smartHome' },
  { value: 'grafana', icon: Activity, category: 'smartHome' },
  { value: 'nodered', icon: Activity, category: 'smartHome' },

  // Cloud Platforms (1)
  { value: 'supabase', icon: Zap, category: 'databases' },

  // Management Tools
  { value: 'portainer', icon: Package, category: 'management' },
  { value: 'syncthing', icon: Activity, category: 'management' },
]

// Group source types by category for better UX
const SOURCE_CATEGORIES = SOURCE_TYPES.reduce((acc, type) => {
  if (!acc[type.category]) acc[type.category] = []
  acc[type.category].push(type)
  return acc
}, {})

export default function SourceModal({ isOpen, onClose, onSave, editingSource }) {
  const { t } = useTranslation()
  const [showPassword, setShowPassword] = useState(false)
  const [showToken, setShowToken] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState('network')
  const [searchQuery, setSearchQuery] = useState('')
  const [connectionTestStatus, setConnectionTestStatus] = useState(null) // null, 'testing', 'success', 'error'
  const [connectionTestMessage, setConnectionTestMessage] = useState('')
  const [credentialProfiles, setCredentialProfiles] = useState({})
  // A source without its own schedule inherits the global default.
  const [useDefaultSchedule, setUseDefaultSchedule] = useState(true)
  const [defaultSchedule, setDefaultSchedule] = useState(DEFAULT_SCHEDULE)
  const [formData, setFormData] = useState({
    name: '',
    type: 'nas',
    enabled: true,
    priority: 1,
    schedule: { ...DEFAULT_SCHEDULE },
    config: {}
  })

  useEffect(() => {
    if (editingSource) {
      setFormData({
        ...editingSource,
        schedule: editingSource.schedule || { ...DEFAULT_SCHEDULE }
      })
      setUseDefaultSchedule(!editingSource.schedule)
      // Set category based on type
      const sourceType = SOURCE_TYPES.find(t => t.value === editingSource.type)
      if (sourceType) setSelectedCategory(sourceType.category)
    } else {
      // Reset form
      setFormData({
        name: '',
        type: 'nas',
        enabled: true,
        priority: 1,
        schedule: { ...DEFAULT_SCHEDULE },
        config: {}
      })
      setUseDefaultSchedule(true)
      setSelectedCategory('network')
    }
  }, [editingSource, isOpen])

  // Load credential profiles when modal opens
  useEffect(() => {
    if (isOpen) {
      settingsAPI.getCredentials().then(res => {
        setCredentialProfiles(res.data)
      }).catch(() => {})
      sourcesAPI.getSchedules().then(res => {
        if (res.data?.default) setDefaultSchedule(res.data.default)
      }).catch(() => {})
    }
  }, [isOpen])

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(normalizeSourceData(formData))
  }

  const splitList = (value) => {
    if (Array.isArray(value)) return value
    if (!value) return []
    return String(value).split(',').map(item => item.trim()).filter(Boolean)
  }

  const normalizeSourceData = (source) => {
    const config = { ...(source.config || {}) }
    const normalized = { ...source, config }

    // Dropping the key lets the backend fall back to the global default,
    // so the source keeps following it when the default changes later.
    if (useDefaultSchedule) {
      delete normalized.schedule
    }

    if (config.credential_profile) {
      normalized.credential_profile = config.credential_profile
      delete config.credential_profile
    }

    if (source.type === 'local' && config.path) {
      normalized.sources = [config.path]
    }

    if (source.type === 'sqlite' && config.path) {
      normalized.databases = [config.path]
    }

    if (['mysql', 'postgresql', 'couchdb'].includes(source.type) && config.database) {
      normalized.databases = [config.database]
    }

    if (source.type === 'docker-volume') {
      normalized.volumes = splitList(config.volumes)
    }

    if (source.type === 'docker-image') {
      normalized.images = splitList(config.images)
    }

    if (['gitlab', 'gitea', 'forgejo', 'bitbucket', 'codeberg'].includes(source.type)) {
      normalized.repositories = splitList(config.repo)
      if (config.host) normalized.host = config.host
      if (config.token) normalized.token = config.token
    }

    if (source.type === 'nas' && config.host && config.share) {
      normalized.source = `//${config.host}/${String(config.share).replace(/^\/+/, '')}`
    }

    if (['homeassistant', 'grafana', 'nodered', 'portainer', 'syncthing'].includes(source.type)) {
      config.backup_method = 'api'
      if (source.type === 'portainer' && config.https === undefined) {
        config.https = true
      }
    }

    return normalized
  }

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleConfigChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      config: { ...prev.config, [field]: value }
    }))
  }

  const handleTypeChange = (type) => {
    const sourceType = SOURCE_TYPES.find(sourceType => sourceType.value === type)
    if (sourceType) setSelectedCategory(sourceType.category)
    setFormData(prev => ({
      ...prev,
      type,
      config: {} // Reset config when type changes
    }))
  }

  if (!isOpen) return null

  // Credential profile selector component
  const CredentialProfileSelect = ({ provider, label }) => {
    const profiles = credentialProfiles[provider]?.profiles || []
    if (profiles.length === 0) {
      return (
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <p className="text-sm text-amber-800">
            {t('sourceForm.credentialMissing', { label })}
          </p>
        </div>
      )
    }
    if (profiles.length === 1) {
      return (
        <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-800">
            {t('sourceForm.profileUsed', { label, profile: profiles[0].profile })}
          </p>
        </div>
      )
    }
    return (
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          {t('sourceForm.selectProfile', { label })}
        </label>
        <select
          className="input"
          value={formData.config.credential_profile || ''}
          onChange={(e) => handleConfigChange('credential_profile', e.target.value)}
        >
          <option value="">{t('sourceForm.automaticProfile')}</option>
          {profiles.map(p => (
            <option key={p.profile} value={p.profile}>{p.profile}</option>
          ))}
        </select>
      </div>
    )
  }
  CredentialProfileSelect.propTypes = {
    provider: PropTypes.string.isRequired,
    label: PropTypes.string.isRequired,
  }

  // Get config fields based on selected type
  const renderConfigFields = () => {
    const type = formData.type

    // Network Storage Types
    if (type === 'nas') {
      return (
        <div className="space-y-4">
          <CredentialProfileSelect provider="nas" label="NAS" />
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.hostIp')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.host || ''}
              onChange={(e) => handleConfigChange('host', e.target.value)}
              placeholder="192.168.1.100"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.shareName')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.share || ''}
              onChange={(e) => handleConfigChange('share', e.target.value)}
              placeholder="backup"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.remotePath')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.path || ''}
              onChange={(e) => handleConfigChange('path', e.target.value)}
              placeholder="/backups"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.username')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.username || ''}
              onChange={(e) => handleConfigChange('username', e.target.value)}
              placeholder="nas_user"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.password')}</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                className="input pr-10"
                value={formData.config.password || ''}
                onChange={(e) => handleConfigChange('password', e.target.value)}
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700"
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>
      )
    }

    if (type === 'nfs') {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.hostIp')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.host || ''}
              onChange={(e) => handleConfigChange('host', e.target.value)}
              placeholder="192.168.1.100"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.exportPath')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.share || ''}
              onChange={(e) => handleConfigChange('share', e.target.value)}
              placeholder="/exports/backup"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.remotePath')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.path || ''}
              onChange={(e) => handleConfigChange('path', e.target.value)}
              placeholder="/data"
            />
          </div>
        </div>
      )
    }

    if (type === 'rsync-ssh') {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.host')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.host || ''}
              onChange={(e) => handleConfigChange('host', e.target.value)}
              placeholder="192.168.1.100"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.port')}</label>
            <input
              type="number"
              className="input"
              value={formData.config.port || 22}
              onChange={(e) => handleConfigChange('port', parseInt(e.target.value))}
              placeholder="22"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.remotePathRequired')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.path || ''}
              onChange={(e) => handleConfigChange('path', e.target.value)}
              placeholder="/volume1/backup"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.username')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.username || ''}
              onChange={(e) => handleConfigChange('username', e.target.value)}
              placeholder="backup_user"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.sshKeyPath')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.ssh_key_path || ''}
              onChange={(e) => handleConfigChange('ssh_key_path', e.target.value)}
              placeholder="~/.ssh/id_rsa"
            />
            <p className="text-xs text-gray-500 mt-1">{t('sourceForm.sshKeyHint')}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.password')}</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                className="input pr-10"
                value={formData.config.password || ''}
                onChange={(e) => handleConfigChange('password', e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700"
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>
      )
    }

    if (type === 'webdav') {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.host')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.host || ''}
              onChange={(e) => handleConfigChange('host', e.target.value)}
              placeholder="cloud.example.com"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.path')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.path || ''}
              onChange={(e) => handleConfigChange('path', e.target.value)}
              placeholder="/remote.php/dav/files/username/Backup"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.username')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.username || ''}
              onChange={(e) => handleConfigChange('username', e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.password')}</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                className="input pr-10"
                value={formData.config.password || ''}
                onChange={(e) => handleConfigChange('password', e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700"
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>
      )
    }

    // Local Storage
    if (type === 'local') {
      return (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.localPath')}</label>
          <input
            type="text"
            className="input"
            value={formData.config.path || ''}
            onChange={(e) => handleConfigChange('path', e.target.value)}
            placeholder="/var/data"
            required
          />
        </div>
      )
    }

    // GitHub with auto-discovery
    if (type === 'github') {
      return (
        <div className="space-y-4">
          <CredentialProfileSelect provider="github" label="GitHub Token" />

          <GitHubRepoSelector
            discoveryMode={formData.config.discovery_mode || 'manual'}
            selectedRepos={formData.config.repositories || []}
            excludeRepos={formData.config.exclude || []}
            onDiscoveryModeChange={(mode) => handleConfigChange('discovery_mode', mode)}
            onSelectedReposChange={(repos) => handleConfigChange('repositories', repos)}
            onExcludeChange={(excludes) => handleConfigChange('exclude', excludes)}
          />
        </div>
      )
    }

    // Other Git Platforms
    if (['gitlab', 'gitea', 'forgejo', 'bitbucket', 'codeberg'].includes(type)) {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {type === 'gitlab' ? t('sourceForm.gitlabInstance') : t('sourceForm.hostOptional')}
            </label>
            <input
              type="text"
              className="input"
              value={formData.config.host || ''}
              onChange={(e) => handleConfigChange('host', e.target.value)}
              placeholder={
                type === 'gitlab' ? 'gitlab.com' :
                type === 'gitea' ? 'gitea.example.com' :
                type === 'forgejo' ? 'forgejo.example.com' :
                type === 'codeberg' ? 'codeberg.org' :
                'bitbucket.org'
              }
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.repositories')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.repo || ''}
              onChange={(e) => handleConfigChange('repo', e.target.value)}
              placeholder="username/repository"
              required
            />
            <p className="text-xs text-gray-500 mt-1">{t('sourceForm.repositoryFormat')}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.accessToken')}</label>
            <div className="relative">
              <input
                type={showToken ? "text" : "password"}
                className="input pr-10"
                value={formData.config.token || ''}
                onChange={(e) => handleConfigChange('token', e.target.value)}
                placeholder={
                  type === 'gitlab' ? 'glpat-xxxxxxxxxxxx' :
                  'xxxxxxxxxxxx'
                }
                required
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700"
              >
                {showToken ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>
      )
    }

    // Databases
    if (['mysql', 'postgresql', 'mongodb', 'redis', 'couchdb', 'influxdb'].includes(type)) {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.host')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.host || 'localhost'}
              onChange={(e) => handleConfigChange('host', e.target.value)}
              placeholder="localhost"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.port')}</label>
            <input
              type="number"
              className="input"
              value={formData.config.port || (
                type === 'mysql' ? 3306 :
                type === 'postgresql' ? 5432 :
                type === 'mongodb' ? 27017 :
                type === 'redis' ? 6379 :
                type === 'couchdb' ? 5984 :
                8086
              )}
              onChange={(e) => handleConfigChange('port', parseInt(e.target.value))}
            />
          </div>
          {type !== 'redis' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.databaseName')}</label>
              <input
                type="text"
                className="input"
                value={formData.config.database || ''}
                onChange={(e) => handleConfigChange('database', e.target.value)}
                placeholder={type === 'mongodb' ? 'myapp' : 'production_db'}
              />
              <p className="text-xs text-gray-500 mt-1">{t('sourceForm.databaseEmpty')}</p>
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.username')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.username || ''}
              onChange={(e) => handleConfigChange('username', e.target.value)}
              placeholder={type === 'postgresql' ? 'postgres' : 'root'}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.password')}</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                className="input pr-10"
                value={formData.config.password || ''}
                onChange={(e) => handleConfigChange('password', e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700"
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>
      )
    }

    if (type === 'sqlite') {
      return (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.databaseFilePath')}</label>
          <input
            type="text"
            className="input"
            value={formData.config.path || ''}
            onChange={(e) => handleConfigChange('path', e.target.value)}
            placeholder="/var/lib/app/database.db"
            required
          />
        </div>
      )
    }

    // Cloud Storage (rclone-based)
    if (['gdrive', 'onedrive', 'dropbox', 's3', 'b2', 'icloud', 'box', 'mega', 'pcloud', 'rclone'].includes(type)) {
      // Determine if OAuth2 is needed
      const needsOAuth = !['s3', 'b2'].includes(type)

      return (
        <div className="space-y-4">
          {/* Important Notice */}
          <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
              <div className="text-sm text-blue-800">
                <p className="font-semibold mb-1">
                  {needsOAuth ? t('sourceForm.oauthRequired') : t('sourceForm.apiCredentialsRequired')}
                </p>
                {needsOAuth ? (
                  <>
                    <p className="mb-2">{t('sourceForm.configureRclone')}</p>
                    <code className="block bg-blue-100 p-2 rounded text-xs mb-2">
                      docker exec -it {BRAND.slug}-backend rclone config
                    </code>
                    <p className="text-xs">
                      {t('sourceForm.rcloneAuthHint', {
                        provider: t(`sourceTypes.${type}`)
                      })}
                    </p>
                  </>
                ) : (
                  <p className="text-xs">
                    {t('sourceForm.enterProviderCredentials', {
                      provider: type === 's3' ? 'AWS' : 'Backblaze B2'
                    })}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* rclone Remote Name (for OAuth2 sources) */}
          {needsOAuth && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('sourceForm.rcloneRemoteName')}
              </label>
              <input
                type="text"
                className="input"
                value={formData.config.remote || ''}
                onChange={(e) => handleConfigChange('remote', e.target.value)}
                placeholder={
                  type === 'gdrive' ? 'my-gdrive' :
                  type === 'onedrive' ? 'my-onedrive' :
                  type === 'dropbox' ? 'my-dropbox' :
                  'myremote'
                }
                required
              />
              <p className="text-xs text-gray-500 mt-1">
                {t('sourceForm.rcloneRemoteHint')}
              </p>
            </div>
          )}

          {/* S3/B2 Credentials */}
          {!needsOAuth && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {type === 's3' ? 'AWS Access Key ID *' : t('sourceForm.applicationKeyId')}
                </label>
                <input
                  type="text"
                  className="input"
                  value={formData.config.access_key || ''}
                  onChange={(e) => handleConfigChange('access_key', e.target.value)}
                  placeholder={type === 's3' ? 'AKIAIOSFODNN7EXAMPLE' : 'Your B2 Key ID'}
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {type === 's3' ? 'AWS Secret Access Key *' : t('sourceForm.applicationKey')}
                </label>
                <div className="relative">
                  <input
                    type={showApiKey ? "text" : "password"}
                    className="input pr-10"
                    value={formData.config.secret_key || ''}
                    onChange={(e) => handleConfigChange('secret_key', e.target.value)}
                    placeholder={t('sourceForm.secretKey')}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700"
                  >
                    {showApiKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>
              {type === 's3' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.region')}</label>
                    <input
                      type="text"
                      className="input"
                      value={formData.config.region || 'us-east-1'}
                      onChange={(e) => handleConfigChange('region', e.target.value)}
                      placeholder="us-east-1"
                      required
                    />
                    <p className="text-xs text-gray-500 mt-1">{t('sourceForm.regionHint')}</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.bucketName')}</label>
                    <input
                      type="text"
                      className="input"
                      value={formData.config.bucket || ''}
                      onChange={(e) => handleConfigChange('bucket', e.target.value)}
                      placeholder="my-backup-bucket"
                      required
                    />
                  </div>
                </>
              )}
              {type === 'b2' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.bucketName')}</label>
                  <input
                    type="text"
                    className="input"
                    value={formData.config.bucket || ''}
                    onChange={(e) => handleConfigChange('bucket', e.target.value)}
                    placeholder="my-b2-bucket"
                    required
                  />
                </div>
              )}
            </>
          )}

          {/* Folder Path */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.folderPath')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.path || ''}
              onChange={(e) => handleConfigChange('path', e.target.value)}
              placeholder={
                type === 's3' || type === 'b2' ? '/backups' :
                type === 'gdrive' ? 'Backups/MyFolder' :
                type === 'onedrive' ? 'Documents/Backups' :
                type === 'dropbox' ? '/Backups' :
                '/Backups'
              }
              required
            />
            <p className="text-xs text-gray-500 mt-1">
              {type === 's3' || type === 'b2'
                ? t('sourceForm.bucketPathHint')
                : t('sourceForm.cloudPathHint', { provider: t(`sourceTypes.${type}`) })}
            </p>
          </div>
        </div>
      )
    }

    // FTP/SFTP
    if (['ftp', 'sftp'].includes(type)) {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.host')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.host || ''}
              onChange={(e) => handleConfigChange('host', e.target.value)}
              placeholder="ftp.example.com"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.port')}</label>
            <input
              type="number"
              className="input"
              value={formData.config.port || (type === 'ftp' ? 21 : 22)}
              onChange={(e) => handleConfigChange('port', parseInt(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.remotePath')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.path || ''}
              onChange={(e) => handleConfigChange('path', e.target.value)}
              placeholder="/backup"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.username')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.username || ''}
              onChange={(e) => handleConfigChange('username', e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {type === 'sftp' ? t('sourceForm.passwordOrSshKey') : t('sourceForm.password')}
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                className="input pr-10"
                value={formData.config.password || ''}
                onChange={(e) => handleConfigChange('password', e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700"
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>
      )
    }

    // Docker
    if (type === 'docker-volume') {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.volumeNames')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.volumes || ''}
              onChange={(e) => handleConfigChange('volumes', e.target.value)}
              placeholder="mysql_data, nginx_config, app_uploads"
              required
            />
            <p className="text-xs text-gray-500 mt-1">{t('sourceForm.volumeHint')}</p>
          </div>
        </div>
      )
    }

    if (type === 'docker-image') {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.imageNames')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.images || ''}
              onChange={(e) => handleConfigChange('images', e.target.value)}
              placeholder="nginx:latest, mysql:8.0, myapp:production"
              required
            />
            <p className="text-xs text-gray-500 mt-1">{t('sourceForm.imageHint')}</p>
          </div>
        </div>
      )
    }

    // Self-Hosted Services - Generic config for all
    if (['homeassistant', 'grafana', 'nodered', 'portainer', 'syncthing'].includes(type)) {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.host')}</label>
            <input
              type="text"
              className="input"
              value={formData.config.host || 'localhost'}
              onChange={(e) => handleConfigChange('host', e.target.value)}
              placeholder="192.168.1.100"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.port')}</label>
            <input
              type="number"
              className="input"
              value={formData.config.port || (
                type === 'homeassistant' ? 8123 :
                type === 'grafana' ? 3000 :
                type === 'portainer' ? 9443 :
                8080
              )}
              onChange={(e) => handleConfigChange('port', parseInt(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('sourceForm.apiKeyToken')}
            </label>
            <div className="relative">
              <input
                type={showApiKey ? "text" : "password"}
                className="input pr-10"
                value={formData.config.api_key || formData.config.token || ''}
                onChange={(e) => handleConfigChange('api_key', e.target.value)}
                placeholder={t('sourceForm.apiKeyPlaceholder')}
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700"
              >
                {showApiKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>
          {type === 'portainer' && (
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={formData.config.options?.verify_ssl !== false}
                onChange={(e) => handleConfigChange('options', {
                  ...formData.config.options,
                  verify_ssl: e.target.checked
                })}
              />
              <span className="text-sm text-gray-700">{t('sourceForm.tlsVerify')}</span>
            </label>
          )}
        </div>
      )
    }

    // Supabase
    if (type === 'supabase') {
      const testConnection = async () => {
        setConnectionTestStatus('testing')
        setConnectionTestMessage('')
        try {
          const testData = {
            profile: formData.config.credential_profile || '',
          }
          const response = await sourcesAPI.testSupabase(testData)
          setConnectionTestStatus('success')
          setConnectionTestMessage(response.data.message || t('sources.testSuccess'))
        } catch (error) {
          setConnectionTestStatus('error')
          setConnectionTestMessage(error.response?.data?.error || t('sources.testError'))
        }
      }

      return (
        <div className="space-y-4">
          <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-900 font-semibold mb-2">{t('sourceForm.supabaseIntro')}</p>
            <ol className="text-xs text-blue-800 space-y-1 list-decimal list-inside">
              <li>{t('sourceForm.supabaseStep1')}</li>
              <li>{t('sourceForm.supabaseStep2')}</li>
              <li>{t('sourceForm.supabaseStep3')}</li>
              <li>{t('sourceForm.supabaseStep4')}</li>
            </ol>
          </div>

          <CredentialProfileSelect provider="supabase" label="Supabase" />

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('sourceForm.backupMode')}</label>
            <select
              className="input"
              value={formData.config.backup_mode || 'db_only'}
              onChange={(e) => handleConfigChange('backup_mode', e.target.value)}
            >
              <option value="db_only">{t('sourceForm.dbOnly')}</option>
              <option value="full">{t('sourceForm.full')}</option>
            </select>
          </div>

          {formData.config.backup_mode === 'full' && (
            <div className="space-y-3 pl-4 border-l-2 border-blue-200">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                  checked={formData.config.options?.include_storage !== false}
                  onChange={(e) => handleConfigChange('options', {
                    ...formData.config.options,
                    include_storage: e.target.checked
                  })}
                />
                <span className="text-sm text-gray-700">{t('sourceForm.includeStorage')}</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                  checked={formData.config.options?.include_auth_config !== false}
                  onChange={(e) => handleConfigChange('options', {
                    ...formData.config.options,
                    include_auth_config: e.target.checked
                  })}
                />
                <span className="text-sm text-gray-700">{t('sourceForm.includeAuth')}</span>
              </label>
            </div>
          )}

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
              checked={formData.config.options?.compress !== false}
              onChange={(e) => handleConfigChange('options', {
                ...formData.config.options,
                compress: e.target.checked
              })}
            />
            <span className="text-sm text-gray-700">{t('sourceForm.compress')}</span>
          </label>

          {/* Connection Test Button */}
          <div className="pt-2">
            <button
              type="button"
              onClick={testConnection}
              disabled={connectionTestStatus === 'testing'}
              className={clsx(
                'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                connectionTestStatus === 'success'
                  ? 'bg-green-100 text-green-700 border border-green-300'
                  : connectionTestStatus === 'error'
                  ? 'bg-red-100 text-red-700 border border-red-300'
                  : 'bg-gray-100 text-gray-700 border border-gray-300 hover:bg-gray-200',
                connectionTestStatus === 'testing' && 'opacity-50 cursor-not-allowed'
              )}
            >
              {connectionTestStatus === 'testing' ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : connectionTestStatus === 'success' ? (
                <CheckCircle className="w-4 h-4" />
              ) : connectionTestStatus === 'error' ? (
                <AlertCircle className="w-4 h-4" />
              ) : (
                <Zap className="w-4 h-4" />
              )}
              {connectionTestStatus === 'testing' ? t('sources.testing') : t('sources.testConnection')}
            </button>
            {connectionTestMessage && (
              <p className={clsx(
                'text-xs mt-2',
                connectionTestStatus === 'success' ? 'text-green-600' : 'text-red-600'
              )}>
                {connectionTestMessage}
              </p>
            )}
          </div>
        </div>
      )
    }

    // Default fallback
    return (
      <div className="p-4 bg-blue-50 rounded-lg">
        <p className="text-sm text-blue-700">
          {t('sourceForm.unavailable')}
        </p>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="modal-stage">
        <div className="modal-panel max-w-4xl">
          {/* Header */}
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-200 bg-white px-4 py-4 md:px-6 dark:border-gray-800 dark:bg-gray-900">
            <h2 className="min-w-0 truncate text-lg font-bold text-gray-900 md:text-xl">
              {editingSource ? t('sourceForm.editTitle') : t('sources.addSource')}
            </h2>
            <button
              onClick={onClose}
              className="icon-btn hover:bg-gray-100 dark:hover:bg-gray-800"
              aria-label={t('common.close')}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="p-4 md:p-6 space-y-4 md:space-y-6">
            {/* Basic Info */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('sourceForm.sourceName')}
                </label>
                <input
                  type="text"
                  className="input"
                  value={formData.name}
                  onChange={(e) => handleChange('name', e.target.value)}
                  placeholder={t('sourceForm.sourceNamePlaceholder')}
                  required
                />
              </div>

              {/* Category Tabs */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('sourceForm.sourceTypeCount', { count: SOURCE_TYPES.length })}
                </label>

                {/* Search Field */}
                <div className="relative mb-3">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    className="input pl-10 pr-10"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={t('sourceForm.searchPlaceholder')}
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => setSearchQuery('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-gray-400 hover:text-gray-600"
                      aria-label={t('common.clear')}
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>

                {(() => {
                  const q = searchQuery.toLowerCase().trim()

                  if (q) {
                    // Search mode: show all matching types grouped by category
                    const filtered = SOURCE_TYPES.filter(sourceType =>
                      t(`sourceTypes.${sourceType.value}`).toLowerCase().includes(q) ||
                      t(`sourceCategories.${sourceType.category}`).toLowerCase().includes(q) ||
                      sourceType.value.toLowerCase().includes(q)
                    )
                    const groupedResults = filtered.reduce((acc, t) => {
                      if (!acc[t.category]) acc[t.category] = []
                      acc[t.category].push(t)
                      return acc
                    }, {})

                    if (filtered.length === 0) {
                      return (
                        <div className="text-center py-6 text-gray-500 text-sm">
                          {t('sourceForm.noSourceType', { query: searchQuery })}
                        </div>
                      )
                    }

                    return (
                      <div className="space-y-3">
                        {Object.entries(groupedResults).map(([category, types]) => (
                          <div key={category}>
                            <p className="text-xs font-semibold text-gray-500 uppercase mb-2">
                              {t(`sourceCategories.${category}`)}
                            </p>
                            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                              {types.map(({ value, icon: Icon }) => (
                                <button
                                  key={value}
                                  type="button"
                                  onClick={() => { handleTypeChange(value); setSearchQuery('') }}
                                  className={clsx(
                                    'flex min-h-24 flex-col items-center justify-center gap-2 rounded-lg border-2 p-3 text-left transition-all',
                                    formData.type === value
                                      ? 'border-primary-600 bg-primary-50'
                                      : 'border-gray-200 hover:border-gray-300'
                                  )}
                                >
                                  <Icon className={clsx(
                                    'w-5 h-5 md:w-6 md:h-6',
                                    formData.type === value ? 'text-primary-600' : 'text-gray-600'
                                  )} />
                                  <span className={clsx(
                                    'text-center text-xs font-medium leading-snug md:text-sm',
                                    formData.type === value ? 'text-primary-700' : 'text-gray-700'
                                  )}>
                                    {t(`sourceTypes.${value}`)}
                                  </span>
                                </button>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )
                  }

                  // Normal category mode
                  return (
                    <>
                      {/* Category Selector */}
                      <div className="mb-3 flex gap-2 overflow-x-auto pb-2">
                        {Object.keys(SOURCE_CATEGORIES).map((category) => (
                          <button
                            key={category}
                            type="button"
                            onClick={() => setSelectedCategory(category)}
                            className={clsx(
                              'min-h-9 shrink-0 rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap transition-all',
                              selectedCategory === category
                                ? 'bg-primary-600 text-white'
                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                            )}
                          >
                            {t(`sourceCategories.${category}`)} ({SOURCE_CATEGORIES[category].length})
                          </button>
                        ))}
                      </div>

                      {/* Type Grid */}
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                        {SOURCE_CATEGORIES[selectedCategory]?.map(({ value, icon: Icon }) => (
                          <button
                            key={value}
                            type="button"
                            onClick={() => handleTypeChange(value)}
                            className={clsx(
                              'flex min-h-24 flex-col items-center justify-center gap-2 rounded-lg border-2 p-3 text-left transition-all',
                              formData.type === value
                                ? 'border-primary-600 bg-primary-50'
                                : 'border-gray-200 hover:border-gray-300'
                            )}
                          >
                            <Icon className={clsx(
                              'w-5 h-5 md:w-6 md:h-6',
                              formData.type === value ? 'text-primary-600' : 'text-gray-600'
                            )} />
                            <span className={clsx(
                              'text-center text-xs font-medium leading-snug md:text-sm',
                              formData.type === value ? 'text-primary-700' : 'text-gray-700'
                            )}>
                              {t(`sourceTypes.${value}`)}
                            </span>
                          </button>
                        ))}
                      </div>
                    </>
                  )
                })()}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {t('sources.priority')}
                  </label>
                  <input
                    type="number"
                    className="input"
                    value={formData.priority}
                    onChange={(e) => handleChange('priority', parseInt(e.target.value))}
                    min="1"
                    max="100"
                  />
                  <p className="text-xs text-gray-500 mt-1">{t('sourceForm.priorityHint')}</p>
                </div>

                <div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                      checked={formData.enabled}
                      onChange={(e) => handleChange('enabled', e.target.checked)}
                    />
                    <span className="text-sm font-medium text-gray-700">
                      {t('sources.enabled')}
                    </span>
                  </label>
                  <p className="text-xs text-gray-500 mt-1">{t('sourceForm.enabledHint')}</p>
                </div>
              </div>
            </div>

            {/* Schedule */}
            <div className="border-t border-gray-200 pt-4 md:pt-6 dark:border-gray-800">
              <h3 className="text-base md:text-lg font-semibold text-gray-900 mb-1 dark:text-gray-100">
                {t('schedule.title')}
              </h3>
              <p className="text-xs text-gray-500 mb-3">{t('schedule.hint')}</p>

              <label className="flex items-center gap-2 cursor-pointer mb-3">
                <input
                  type="checkbox"
                  className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                  checked={useDefaultSchedule}
                  onChange={(e) => setUseDefaultSchedule(e.target.checked)}
                />
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('schedule.useDefault')}
                </span>
              </label>

              {useDefaultSchedule ? (
                <div className="p-3 bg-gray-50 border border-gray-200 rounded-lg dark:bg-gray-800 dark:border-gray-700">
                  <p className="text-sm text-gray-700 dark:text-gray-300">
                    {describeSchedule(defaultSchedule, t)}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">{t('schedule.useDefaultHint')}</p>
                </div>
              ) : (
                <ScheduleFields
                  value={formData.schedule}
                  onChange={(schedule) => handleChange('schedule', schedule)}
                />
              )}
            </div>

            {/* Type-specific config */}
            <div className="border-t border-gray-200 pt-4 md:pt-6">
              <h3 className="text-base md:text-lg font-semibold text-gray-900 mb-3">{t('sourceForm.configuration')}</h3>
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg mb-4">
                <p className="text-xs text-amber-800">
                  {t('sourceForm.credentialNotice')}
                </p>
              </div>
              {renderConfigFields()}
            </div>

            {/* Actions */}
            <div className="sticky bottom-0 -mx-4 -mb-4 flex flex-col-reverse gap-3 border-t border-gray-200 bg-white/95 px-4 py-4 backdrop-blur sm:mx-0 sm:mb-0 sm:flex-row sm:justify-end md:-mx-6 md:px-6 dark:border-gray-800 dark:bg-gray-900/95">
              <button
                type="button"
                onClick={onClose}
                className="btn btn-secondary w-full sm:w-auto"
              >
                {t('common.cancel')}
              </button>
              <button
                type="submit"
                className="btn btn-primary w-full sm:w-auto"
              >
                {editingSource ? t('common.save') : t('common.add')}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}

SourceModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  onSave: PropTypes.func.isRequired,
  editingSource: PropTypes.shape({
    type: PropTypes.string,
    schedule: PropTypes.object,
  }),
}
