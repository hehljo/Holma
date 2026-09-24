import axios from 'axios'
import i18n from '../i18n'

const API_URL = import.meta.env.VITE_API_URL || '/api/v1'

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add token and language to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  // Add Accept-Language header for backend i18n
  const language = i18n.language || 'en'
  config.headers['Accept-Language'] = language

  return config
})

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Don't logout on source connection test failures (e.g. wrong DB password)
      const url = error.config?.url || ''
      const isConnectionTest = url.includes('/test') || url.includes('/discover')
      if (!isConnectionTest) {
        localStorage.removeItem('token')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// Auth API
export const authAPI = {
  login: (username, password) =>
    api.post('/auth/login', { username, password }),

  register: (username, password) =>
    api.post('/auth/register', { username, password }),

  getCurrentUser: () =>
    api.get('/auth/me'),

  changePassword: (currentPassword, newPassword) =>
    api.put('/auth/password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),

  setupStatus: () =>
    api.get('/auth/setup/status'),

  setupOwner: (username, password, setupCode) =>
    api.post('/auth/setup', { username, password, setup_code: setupCode }),
}

// Backup API
export const backupAPI = {
  start: (data) =>
    api.post('/backup/start', data),

  getStatus: (backupId) =>
    api.get(`/backup/${backupId}`),

  getHistory: (limit = 20, offset = 0) =>
    api.get(`/backup/history?limit=${limit}&offset=${offset}`),

  stop: (backupId) =>
    api.post(`/backup/${backupId}/stop`),

  getStats: () =>
    api.get('/backup/stats'),

  getRunningSources: () =>
    api.get('/backup/running-sources'),

  deleteAll: () =>
    api.delete('/backup/all?confirm=true'),
}

// Sources API
export const sourcesAPI = {
  getAll: () =>
    api.get('/sources'),

  getOne: (sourceId) =>
    api.get(`/sources/${sourceId}`),

  create: (data) =>
    api.post('/sources', data),

  update: (sourceId, data) =>
    api.put(`/sources/${sourceId}`, data),

  delete: (sourceId) =>
    api.delete(`/sources/${sourceId}`),

  test: (sourceId) =>
    api.post(`/sources/${sourceId}/test`),

  getSchedules: () =>
    api.get('/sources/schedules'),

  updateDefaultSchedule: (data) =>
    api.put('/sources/schedules/default', data),

  testSupabase: (data) =>
    api.post('/sources/supabase/test', data),

  discoverGitHub: () =>
    api.get('/sources/github/discover'),
}

// Restore API
export const restoreAPI = {
  getAvailable: (sourceId) =>
    api.get(`/backup/restore/available/${sourceId}`),

  start: (data) =>
    api.post('/backup/restore', data),

  getStatus: (restoreId, config = {}) =>
    api.get(`/backup/restore/${restoreId}`, config),
}

// Download API
export const downloadAPI = {
  listFiles: (sourceId) =>
    api.get(`/backup/download/${sourceId}`),

  getDownloadUrl: (sourceId, filename) =>
    `${API_URL}/backup/download/${encodeURIComponent(sourceId)}/${encodeURIComponent(filename)}`,
}

// Settings API
export const settingsAPI = {
  get: () =>
    api.get('/settings'),

  update: (data) =>
    api.put('/settings', data),

  getCredentials: () =>
    api.get('/settings/credentials'),

  updateCredentials: (data) =>
    api.put('/settings/credentials', data),

  addCredentialProfile: (provider, profile, values) =>
    api.post('/settings/credentials/profile', { provider, profile, values }),

  deleteCredentialProfile: (provider, profile) =>
    api.delete('/settings/credentials/profile', { data: { provider, profile } }),

  testCredential: (provider, profile) =>
    api.post('/settings/credentials/test', { provider, profile }),

  getLogs: (lines = 200) =>
    api.get(`/settings/logs?lines=${lines}`),

  clearLogs: () =>
    api.post('/settings/logs/clear'),
}

// Config Export/Import API
export const configAPI = {
  export: () =>
    api.get('/config/export', { responseType: 'blob' }),

  import: (data, merge = false) =>
    api.post(`/config/import?merge=${merge}`, data),

  validate: (data) =>
    api.post('/config/validate', data),
}

// Notifications API
export const notificationsAPI = {
  getChannels: () =>
    api.get('/notifications/channels'),

  test: (channel) =>
    api.post('/notifications/test', channel ? { channel } : {}),
}

export default api
