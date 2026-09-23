import { useTranslation } from 'react-i18next'
import { Clock } from 'lucide-react'
import PropTypes from 'prop-types'
import { DEFAULT_SCHEDULE } from './schedule'

const FREQUENCIES = ['hourly', 'daily', 'weekly', 'monthly']

const WEEKDAY_KEYS = [
  'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
]

/**
 * Schedule editor shared by the source modal and the global default in settings.
 * `value` is the schedule object; `onChange` receives the full updated object.
 */
export default function ScheduleFields({ value, onChange, disabled = false }) {
  const { t } = useTranslation()
  const schedule = { ...DEFAULT_SCHEDULE, ...(value || {}) }

  const update = (field, fieldValue) => {
    onChange({ ...schedule, [field]: fieldValue })
  }

  const fieldClass = 'input' + (disabled ? ' opacity-50 cursor-not-allowed' : '')

  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
          checked={!!schedule.enabled}
          disabled={disabled}
          onChange={(e) => update('enabled', e.target.checked)}
        />
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {t('schedule.enabled')}
        </span>
      </label>

      {schedule.enabled && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('schedule.frequency')}
            </label>
            <select
              className={fieldClass}
              value={schedule.frequency}
              disabled={disabled}
              onChange={(e) => update('frequency', e.target.value)}
            >
              {FREQUENCIES.map((freq) => (
                <option key={freq} value={freq}>{t(`schedule.${freq}`)}</option>
              ))}
            </select>
          </div>

          {schedule.frequency === 'hourly' ? (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('schedule.minute')}
              </label>
              <input
                type="number"
                min="0"
                max="59"
                className={fieldClass}
                value={schedule.minute}
                disabled={disabled}
                onChange={(e) => update('minute', Number(e.target.value))}
              />
              <p className="text-xs text-gray-500 mt-1">{t('schedule.minuteHint')}</p>
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('schedule.time')}
              </label>
              <input
                type="time"
                className={fieldClass}
                value={schedule.time}
                disabled={disabled}
                onChange={(e) => update('time', e.target.value)}
              />
            </div>
          )}

          {schedule.frequency === 'weekly' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('schedule.weekday')}
              </label>
              <select
                className={fieldClass}
                value={schedule.weekday}
                disabled={disabled}
                onChange={(e) => update('weekday', Number(e.target.value))}
              >
                {WEEKDAY_KEYS.map((key, index) => (
                  <option key={key} value={index}>{t(`schedule.${key}`)}</option>
                ))}
              </select>
            </div>
          )}

          {schedule.frequency === 'monthly' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('schedule.day')}
              </label>
              <input
                type="number"
                min="1"
                max="28"
                className={fieldClass}
                value={schedule.day}
                disabled={disabled}
                onChange={(e) => update('day', Number(e.target.value))}
              />
              <p className="text-xs text-gray-500 mt-1">{t('schedule.dayHint')}</p>
            </div>
          )}
        </div>
      )}

      {schedule.enabled && (
        <p className="text-xs text-gray-500 flex items-start gap-1.5">
          <Clock className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
          <span>{t('schedule.timezoneHint')}</span>
        </p>
      )}
    </div>
  )
}

ScheduleFields.propTypes = {
  value: PropTypes.shape({
    enabled: PropTypes.bool,
    frequency: PropTypes.string,
    time: PropTypes.string,
    minute: PropTypes.number,
    weekday: PropTypes.number,
    day: PropTypes.number,
  }),
  onChange: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
}
