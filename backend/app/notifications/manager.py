"""
Notification Manager
Coordinates notifications across multiple channels
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime
import os

from .base import NotificationChannel, NotificationPriority, NotificationType
from app.brand import BRAND_NAME

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages notification delivery across multiple channels"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize notification manager

        Args:
            config_path: Path to notification configuration file
        """
        self.channels: List[NotificationChannel] = []
        self.config_path = config_path or os.environ.get('NOTIFICATION_CONFIG_PATH', '/app/config/notifications.json')
        self.load_channels()

    def load_channels(self):
        """Load and initialize notification channels from configuration"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Notification config not found: {self.config_path}")
                return

            from app.notification_config import load_notification_config
            config = load_notification_config(self.config_path)

            # Import channel classes dynamically
            from .channels import (
                EmailNotification,
                WebhookNotification,
                TelegramNotification,
                NtfyNotification,
                AppriseNotification
            )

            channel_types = {
                'email': EmailNotification,
                'webhook': WebhookNotification,
                'telegram': TelegramNotification,
                'ntfy': NtfyNotification,
                'apprise': AppriseNotification,
            }

            for channel_config in config.get('channels', []):
                channel_type = channel_config.get('type')
                if channel_type in channel_types:
                    try:
                        channel = channel_types[channel_type](channel_config)

                        # Validate configuration
                        is_valid, error = channel.validate_config()
                        if is_valid:
                            self.channels.append(channel)
                            logger.info(f"Loaded notification channel: {channel.name} ({channel_type})")
                        else:
                            logger.error(f"Invalid config for {channel_type}: {error}")
                    except Exception as e:
                        logger.error(
                            'Failed to initialize %s channel: %s',
                            channel_type, type(e).__name__,
                        )
                else:
                    logger.warning(f"Unknown notification channel type: {channel_type}")

        except Exception as e:
            logger.error('Failed to load notification config: %s', type(e).__name__)

    def notify(self,
               title: str,
               message: str,
               priority: NotificationPriority = NotificationPriority.NORMAL,
               notification_type: NotificationType = NotificationType.BACKUP_COMPLETED,
               data: Optional[Dict] = None,
               channels: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        Send notification to all or specified channels

        Args:
            title: Notification title
            message: Notification message
            priority: Priority level
            notification_type: Type of notification
            data: Additional contextual data
            channels: List of specific channel names to notify (None = all)

        Returns:
            dict: Channel name -> success status
        """
        results = {}

        # Filter channels
        target_channels = self.channels
        if channels:
            target_channels = [c for c in self.channels if c.name in channels]

        # Filter by enabled status
        target_channels = [c for c in target_channels if c.is_enabled()]

        if not target_channels:
            logger.warning("No enabled notification channels available")
            return results

        # Send to each channel
        for channel in target_channels:
            try:
                success = channel.send_with_retry(title, message, priority, notification_type, data)
                results[channel.name] = success
            except Exception as e:
                logger.error(
                    'Error sending notification via %s: %s',
                    channel.name, type(e).__name__,
                )
                results[channel.name] = False

        return results

    def notify_backup_started(self, backup_id: str, sources_count: int):
        """Send notification when backup starts"""
        title = "🚀 Backup Started"
        message = f"Backup {backup_id} has started with {sources_count} source(s)."

        self.notify(
            title=title,
            message=message,
            priority=NotificationPriority.NORMAL,
            notification_type=NotificationType.BACKUP_STARTED,
            data={'backup_id': backup_id, 'sources_count': sources_count}
        )

    def notify_backup_completed(self, backup_id: str, duration: int, total_size: int, sources_count: int):
        """Send notification when backup completes successfully"""
        from .base import NotificationChannel

        # Format readable values
        duration_str = NotificationChannel.format_duration(None, duration)
        size_str = NotificationChannel.format_size(None, total_size)

        title = "✅ Backup Completed Successfully"
        message = (
            f"Backup {backup_id} completed successfully!\n\n"
            f"📊 Statistics:\n"
            f"• Sources: {sources_count}\n"
            f"• Duration: {duration_str}\n"
            f"• Total Size: {size_str}\n"
            f"• Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        self.notify(
            title=title,
            message=message,
            priority=NotificationPriority.NORMAL,
            notification_type=NotificationType.BACKUP_COMPLETED,
            data={
                'backup_id': backup_id,
                'duration': duration,
                'total_size': total_size,
                'sources_count': sources_count
            }
        )

    def notify_backup_failed(self, backup_id: str, error_message: str):
        """Send notification when backup fails"""
        title = "❌ Backup Failed"
        message = (
            f"Backup {backup_id} has failed!\n\n"
            f"⚠️ Error: {error_message}\n\n"
            f"Please check the logs for more details."
        )

        self.notify(
            title=title,
            message=message,
            priority=NotificationPriority.HIGH,
            notification_type=NotificationType.BACKUP_FAILED,
            data={
                'backup_id': backup_id,
                'error_message': error_message
            }
        )

    def notify_backup_partial(self, backup_id: str, failed_sources: List[str], total_sources: int):
        """Send notification when backup completes with some failures"""
        title = "⚠️ Backup Completed with Errors"
        message = (
            f"Backup {backup_id} completed with some failures.\n\n"
            f"Failed sources ({len(failed_sources)}/{total_sources}):\n"
        )

        for source in failed_sources[:5]:  # Limit to first 5
            message += f"• {source}\n"

        if len(failed_sources) > 5:
            message += f"• ... and {len(failed_sources) - 5} more\n"

        self.notify(
            title=title,
            message=message,
            priority=NotificationPriority.HIGH,
            notification_type=NotificationType.BACKUP_PARTIAL,
            data={
                'backup_id': backup_id,
                'failed_sources': failed_sources,
                'total_sources': total_sources
            }
        )

    def get_enabled_channels(self) -> List[str]:
        """Get list of enabled channel names"""
        return [c.name for c in self.channels if c.is_enabled()]

    def test_channel(self, channel_name: str) -> bool:
        """
        Test a specific notification channel

        Args:
            channel_name: Name of channel to test

        Returns:
            bool: True if test successful
        """
        channel = next((c for c in self.channels if c.name == channel_name), None)
        if not channel:
            logger.error(f"Channel not found: {channel_name}")
            return False

        return channel.send_with_retry(
            title=f"🧪 {BRAND_NAME} Test Notification",
            message=f"This is a test notification from {BRAND_NAME}. If you receive this, your notification channel is configured correctly!",
            priority=NotificationPriority.NORMAL,
            notification_type=NotificationType.SYSTEM_WARNING
        )
