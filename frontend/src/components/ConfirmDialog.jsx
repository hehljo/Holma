import { AlertTriangle, X } from 'lucide-react'
import clsx from 'clsx'
import { useTranslation } from 'react-i18next'
import PropTypes from 'prop-types'

/**
 * Confirmation Dialog Component
 * Best Practice 11/2025: Always confirm destructive actions
 *
 * @param {boolean} isOpen - Whether dialog is visible
 * @param {function} onClose - Close callback
 * @param {function} onConfirm - Confirm callback
 * @param {string} title - Dialog title
 * @param {string} message - Dialog message
 * @param {string} confirmText - Confirm button text (default: "Confirm")
 * @param {string} confirmVariant - Confirm button variant: "danger" | "warning" | "primary"
 * @param {boolean} isLoading - Show loading state on confirm button
 */
export default function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText,
  cancelText,
  confirmVariant = "danger",
  isLoading = false,
}) {
  const { t } = useTranslation()
  if (!isOpen) return null

  const resolvedTitle = title || t('common.confirm')
  const resolvedConfirmText = confirmText || t('common.confirm')
  const resolvedCancelText = cancelText || t('common.cancel')

  const variantStyles = {
    danger: 'bg-red-600 hover:bg-red-700 focus:ring-red-500',
    warning: 'bg-yellow-600 hover:bg-yellow-700 focus:ring-yellow-500',
    primary: 'bg-primary-600 hover:bg-primary-700 focus:ring-primary-500',
  }

  const iconColors = {
    danger: 'bg-red-100 text-red-600',
    warning: 'bg-yellow-100 text-yellow-600',
    primary: 'bg-primary-100 text-primary-600',
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div className="modal-stage">
        <div
          className="modal-panel max-w-md p-5 md:p-6 transform transition-all"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Close button */}
          <button
            onClick={onClose}
            className="icon-btn absolute top-3 right-3 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            aria-label={t('common.close')}
          >
            <X className="w-5 h-5" />
          </button>

          {/* Icon */}
          <div className={clsx(
            'mx-auto flex items-center justify-center w-12 h-12 rounded-full mb-4',
            iconColors[confirmVariant]
          )}>
            <AlertTriangle className="w-6 h-6" />
          </div>

          {/* Title */}
          <h3 className="text-lg font-semibold text-gray-900 text-center mb-2">
            {resolvedTitle}
          </h3>

          {/* Message */}
          {message && (
            <p className="text-sm text-gray-600 text-center mb-6 break-words">
              {message}
            </p>
          )}

          {/* Actions */}
          <div className="flex flex-col-reverse sm:flex-row gap-3 sm:gap-3">
            <button
              onClick={onClose}
              disabled={isLoading}
              className="btn btn-secondary flex-1 justify-center"
            >
              {resolvedCancelText}
            </button>
            <button
              onClick={() => {
                onConfirm()
                // Don't auto-close - let the parent handle it
              }}
              disabled={isLoading}
              className={clsx(
                'btn flex-1 justify-center text-white focus:ring-2 focus:ring-offset-2',
                variantStyles[confirmVariant],
                isLoading && 'opacity-75 cursor-not-allowed'
              )}
            >
              {isLoading ? t('common.processing') : resolvedConfirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

ConfirmDialog.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  onConfirm: PropTypes.func.isRequired,
  title: PropTypes.string,
  message: PropTypes.string,
  confirmText: PropTypes.string,
  cancelText: PropTypes.string,
  confirmVariant: PropTypes.oneOf(['danger', 'warning', 'primary']),
  isLoading: PropTypes.bool,
}
