/**
 * Skeleton Loading Components
 * Modern loading skeletons for better UX (Nov 2025 best practice)
 */
import clsx from 'clsx'
import PropTypes from 'prop-types'

// Base Skeleton component
export function Skeleton({ className, ...props }) {
  return (
    <div
      className={clsx(
        'animate-pulse bg-gray-200 rounded',
        className
      )}
      {...props}
    />
  )
}

// Card Skeleton for dashboard/sources
export function CardSkeleton() {
  return (
    <div className="card">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3 flex-1">
          <Skeleton className="w-12 h-12 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-4 w-20" />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="w-10 h-10 rounded-lg" />
          <Skeleton className="w-10 h-10 rounded-lg" />
          <Skeleton className="w-10 h-10 rounded-lg" />
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-5 w-16" />
        </div>
        <div className="flex items-center justify-between">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-5 w-12" />
        </div>
      </div>
    </div>
  )
}

// Table Row Skeleton for history
export function TableRowSkeleton() {
  return (
    <div className="border-b border-gray-200 py-3 md:py-4">
      <div className="flex items-center gap-3 md:gap-4">
        <Skeleton className="w-8 h-8 md:w-10 md:h-10 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3 w-32" />
        </div>
        <Skeleton className="h-6 w-20 rounded-full" />
      </div>
    </div>
  )
}

// Stats Card Skeleton for dashboard
export function StatsCardSkeleton() {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-8 w-16" />
        </div>
        <Skeleton className="w-12 h-12 rounded-full" />
      </div>
    </div>
  )
}

// Form Skeleton for settings
export function FormSkeleton() {
  return (
    <div className="space-y-4">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-10 w-full rounded-lg" />
        </div>
      ))}
    </div>
  )
}

// Grid of Cards Skeleton
export function CardGridSkeleton({ count = 4 }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
      {[...Array(count)].map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  )
}

// Grid of Stats Skeleton
export function StatsGridSkeleton({ count = 4 }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
      {[...Array(count)].map((_, i) => (
        <StatsCardSkeleton key={i} />
      ))}
    </div>
  )
}

Skeleton.propTypes = {
  className: PropTypes.string,
}

CardGridSkeleton.propTypes = {
  count: PropTypes.number,
}

StatsGridSkeleton.propTypes = {
  count: PropTypes.number,
}

export default Skeleton
