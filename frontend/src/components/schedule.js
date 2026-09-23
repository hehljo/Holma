export const DEFAULT_SCHEDULE = {
  enabled: false,
  trigger: 'cron',
  frequency: 'daily',
  time: '03:00',
  minute: 0,
  weekday: 0,
  day: 1,
}

const WEEKDAY_KEYS = [
  'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
]

export function describeSchedule(schedule, t) {
  const value = { ...DEFAULT_SCHEDULE, ...(schedule || {}) }
  if (!value.enabled) return t('schedule.never')

  const frequency = t(`schedule.${value.frequency}`)
  if (value.frequency === 'hourly') {
    return `${frequency} — :${String(value.minute).padStart(2, '0')}`
  }
  if (value.frequency === 'weekly') {
    const weekday = t(`schedule.${WEEKDAY_KEYS[value.weekday] || 'monday'}`)
    return `${frequency} — ${weekday}, ${value.time}`
  }
  if (value.frequency === 'monthly') {
    return `${frequency} — ${value.day}. / ${value.time}`
  }
  return `${frequency} — ${value.time}`
}
