"""
Notification channel implementations
"""
import logging
from app.time_utils import utc_iso_z
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional
import os

from .base import NotificationChannel, NotificationPriority, NotificationType
from app.brand import BRAND_ICON_URL, BRAND_NAME, BRAND_TAGLINE

logger = logging.getLogger(__name__)


def _stored_credential(name):
    """Read UI-managed credentials when a channel is built in app context."""
    try:
        from app.api.settings import get_credential
        return get_credential(name)
    except RuntimeError:
        return ''


class EmailNotification(NotificationChannel):
    """Email notification channel using SMTP"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.smtp_host = config.get('smtp_host') or os.getenv('SMTP_HOST')
        self.smtp_port = config.get('smtp_port', 587) or int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = config.get('smtp_user') or os.getenv('SMTP_USER')
        self.smtp_password = (
            _stored_credential('smtp_password')
            or config.get('smtp_password')
            or os.getenv('SMTP_PASSWORD')
        )
        self.from_email = config.get('from_email') or os.getenv('SMTP_FROM')
        self.to_emails = config.get('to_emails', [])
        self.use_tls = config.get('use_tls', True)

    def validate_config(self) -> tuple[bool, Optional[str]]:
        """Validate email configuration"""
        if not self.smtp_host:
            return False, "SMTP host not configured"
        if not self.smtp_user:
            return False, "SMTP user not configured"
        if not self.smtp_password:
            return False, "SMTP password not configured"
        if not self.from_email:
            return False, "From email not configured"
        if not self.to_emails:
            return False, "No recipient emails configured"
        return True, None

    def send(self,
             title: str,
             message: str,
             priority: NotificationPriority = NotificationPriority.NORMAL,
             notification_type: NotificationType = NotificationType.BACKUP_COMPLETED,
             data: Optional[Dict] = None) -> bool:
        """Send email notification"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[{BRAND_NAME}] {title}"
            msg['From'] = self.from_email
            msg['To'] = ', '.join(self.to_emails)

            # Priority header
            if priority == NotificationPriority.URGENT:
                msg['X-Priority'] = '1'
                msg['Importance'] = 'high'

            # Plain text version
            text_part = MIMEText(message, 'plain', 'utf-8')
            msg.attach(text_part)

            # HTML version with styling
            html_message = self._format_html(title, message, notification_type)
            html_part = MIMEText(html_message, 'html', 'utf-8')
            msg.attach(html_part)

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent to {len(self.to_emails)} recipient(s)")
            return True

        except Exception as e:
            logger.error('Failed to send email: %s', type(e).__name__)
            return False

    def _format_html(self, title: str, message: str, notification_type: NotificationType) -> str:
        """Format email as HTML"""
        # Color based on notification type
        color_map = {
            NotificationType.BACKUP_COMPLETED: '#28a745',
            NotificationType.BACKUP_FAILED: '#dc3545',
            NotificationType.BACKUP_PARTIAL: '#ffc107',
            NotificationType.BACKUP_STARTED: '#007bff',
            NotificationType.SYSTEM_WARNING: '#ffc107',
            NotificationType.SYSTEM_ERROR: '#dc3545',
        }
        color = color_map.get(notification_type, '#6c757d')

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="background-color: {color}; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 24px;">{BRAND_NAME}</h1>
                </div>
                <div style="padding: 30px;">
                    <h2 style="color: {color}; margin-top: 0;">{title}</h2>
                    <div style="white-space: pre-wrap; line-height: 1.6; color: #333;">
{message}
                    </div>
                </div>
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 0 0 8px 8px; text-align: center; color: #6c757d; font-size: 12px;">
                    <p style="margin: 0;">{BRAND_NAME} - {BRAND_TAGLINE}</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html


class WebhookNotification(NotificationChannel):
    """Generic webhook notification (supports Discord, Slack, Mattermost, etc.)"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.webhook_url = config.get('webhook_url') or os.getenv('WEBHOOK_URL')
        self.webhook_type = config.get('webhook_type', 'generic')  # discord, slack, mattermost, generic
        self.headers = config.get('headers', {})

    def validate_config(self) -> tuple[bool, Optional[str]]:
        """Validate webhook configuration"""
        if not self.webhook_url:
            return False, "Webhook URL not configured"
        return True, None

    def send(self,
             title: str,
             message: str,
             priority: NotificationPriority = NotificationPriority.NORMAL,
             notification_type: NotificationType = NotificationType.BACKUP_COMPLETED,
             data: Optional[Dict] = None) -> bool:
        """Send webhook notification"""
        try:
            payload = self._format_payload(title, message, notification_type, data)

            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={**self.headers, 'Content-Type': 'application/json'},
                timeout=self.timeout
            )

            if response.status_code in [200, 204]:
                logger.info(f"Webhook notification sent successfully")
                return True
            else:
                logger.error('Webhook returned status %s', response.status_code)
                return False

        except Exception as e:
            logger.error('Failed to send webhook: %s', type(e).__name__)
            return False

    def _format_payload(self, title: str, message: str, notification_type: NotificationType, data: Optional[Dict]) -> Dict:
        """Format payload based on webhook type"""
        if self.webhook_type == 'discord':
            return self._format_discord(title, message, notification_type)
        elif self.webhook_type == 'slack':
            return self._format_slack(title, message, notification_type)
        elif self.webhook_type == 'mattermost':
            return self._format_mattermost(title, message, notification_type)
        else:
            return self._format_generic(title, message, notification_type, data)

    def _format_discord(self, title: str, message: str, notification_type: NotificationType) -> Dict:
        """Format Discord webhook payload"""
        color_map = {
            NotificationType.BACKUP_COMPLETED: 0x28a745,
            NotificationType.BACKUP_FAILED: 0xdc3545,
            NotificationType.BACKUP_PARTIAL: 0xffc107,
            NotificationType.BACKUP_STARTED: 0x007bff,
        }
        color = color_map.get(notification_type, 0x6c757d)

        return {
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,
                "timestamp": utc_iso_z(),
                "footer": {
                    "text": BRAND_NAME,
                    "icon_url": BRAND_ICON_URL
                }
            }]
        }

    def _format_slack(self, title: str, message: str, notification_type: NotificationType) -> Dict:
        """Format Slack webhook payload"""
        color_map = {
            NotificationType.BACKUP_COMPLETED: 'good',
            NotificationType.BACKUP_FAILED: 'danger',
            NotificationType.BACKUP_PARTIAL: 'warning',
            NotificationType.BACKUP_STARTED: '#007bff',
        }
        color = color_map.get(notification_type, '#6c757d')

        return {
            "attachments": [{
                "color": color,
                "title": title,
                "text": message,
                "footer": BRAND_NAME,
                "ts": int(__import__('time').time())
            }]
        }

    def _format_mattermost(self, title: str, message: str, notification_type: NotificationType) -> Dict:
        """Format Mattermost webhook payload"""
        return {
            "text": f"### {title}\n\n{message}",
            "username": BRAND_NAME
        }

    def _format_generic(self, title: str, message: str, notification_type: NotificationType, data: Optional[Dict]) -> Dict:
        """Format generic webhook payload"""
        return {
            "title": title,
            "message": message,
            "type": notification_type.value,
            "timestamp": utc_iso_z(),
            "data": data or {}
        }


class TelegramNotification(NotificationChannel):
    """Telegram bot notification channel"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.bot_token = (
            _stored_credential('telegram_bot_token')
            or config.get('bot_token')
            or os.getenv('TELEGRAM_BOT_TOKEN')
        )
        self.chat_ids = config.get('chat_ids', [])
        self.parse_mode = config.get('parse_mode', 'Markdown')  # HTML or Markdown

    def validate_config(self) -> tuple[bool, Optional[str]]:
        """Validate Telegram configuration"""
        if not self.bot_token:
            return False, "Telegram bot token not configured"
        if not self.chat_ids:
            return False, "No Telegram chat IDs configured"
        return True, None

    def send(self,
             title: str,
             message: str,
             priority: NotificationPriority = NotificationPriority.NORMAL,
             notification_type: NotificationType = NotificationType.BACKUP_COMPLETED,
             data: Optional[Dict] = None) -> bool:
        """Send Telegram notification"""
        try:
            formatted_message = f"*{title}*\n\n{message}" if self.parse_mode == 'Markdown' else f"<b>{title}</b>\n\n{message}"

            success_count = 0
            for chat_id in self.chat_ids:
                payload = {
                    'chat_id': chat_id,
                    'text': formatted_message,
                    'parse_mode': self.parse_mode
                }

                response = requests.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json=payload,
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    success_count += 1
                else:
                    logger.error('Telegram API error: HTTP %s', response.status_code)

            if success_count > 0:
                logger.info(f"Telegram notification sent to {success_count}/{len(self.chat_ids)} chat(s)")
                return True
            return False

        except Exception as e:
            logger.error('Failed to send Telegram notification: %s', type(e).__name__)
            return False


class NtfyNotification(NotificationChannel):
    """ntfy.sh notification channel"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.server_url = config.get('server_url', 'https://ntfy.sh') or os.getenv('NTFY_SERVER_URL', 'https://ntfy.sh')
        self.topic = config.get('topic') or os.getenv('NTFY_TOPIC')
        self.username = config.get('username') or os.getenv('NTFY_USERNAME')
        self.password = config.get('password') or os.getenv('NTFY_PASSWORD')

    def validate_config(self) -> tuple[bool, Optional[str]]:
        """Validate ntfy configuration"""
        if not self.topic:
            return False, "ntfy topic not configured"
        return True, None

    def send(self,
             title: str,
             message: str,
             priority: NotificationPriority = NotificationPriority.NORMAL,
             notification_type: NotificationType = NotificationType.BACKUP_COMPLETED,
             data: Optional[Dict] = None) -> bool:
        """Send ntfy notification"""
        try:
            # Map priority
            priority_map = {
                NotificationPriority.LOW: '2',
                NotificationPriority.NORMAL: '3',
                NotificationPriority.HIGH: '4',
                NotificationPriority.URGENT: '5',
            }

            headers = {
                'Title': title,
                'Priority': priority_map.get(priority, '3'),
                'Tags': self._get_tags(notification_type)
            }

            # Add authentication if configured
            auth = None
            if self.username and self.password:
                auth = (self.username, self.password)

            response = requests.post(
                f"{self.server_url}/{self.topic}",
                data=message.encode('utf-8'),
                headers=headers,
                auth=auth,
                timeout=self.timeout
            )

            if response.status_code == 200:
                logger.info(f"ntfy notification sent to topic '{self.topic}'")
                return True
            else:
                logger.error('ntfy returned status %s', response.status_code)
                return False

        except Exception as e:
            logger.error('Failed to send ntfy notification: %s', type(e).__name__)
            return False

    def _get_tags(self, notification_type: NotificationType) -> str:
        """Get emoji tags for notification type"""
        tag_map = {
            NotificationType.BACKUP_STARTED: 'rocket',
            NotificationType.BACKUP_COMPLETED: 'white_check_mark',
            NotificationType.BACKUP_FAILED: 'x',
            NotificationType.BACKUP_PARTIAL: 'warning',
            NotificationType.SYSTEM_WARNING: 'warning',
            NotificationType.SYSTEM_ERROR: 'x',
        }
        return tag_map.get(notification_type, 'information_source')


class AppriseNotification(NotificationChannel):
    """Apprise integration supporting 80+ notification services"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.urls = config.get('urls', [])  # List of Apprise URLs

        # Try to import apprise
        try:
            import apprise
            self.apprise = apprise.Apprise()
            for url in self.urls:
                self.apprise.add(url)
        except ImportError:
            logger.error("Apprise library not installed. Install with: pip install apprise")
            self.apprise = None

    def validate_config(self) -> tuple[bool, Optional[str]]:
        """Validate Apprise configuration"""
        if not self.apprise:
            return False, "Apprise library not installed"
        if not self.urls:
            return False, "No Apprise URLs configured"
        return True, None

    def send(self,
             title: str,
             message: str,
             priority: NotificationPriority = NotificationPriority.NORMAL,
             notification_type: NotificationType = NotificationType.BACKUP_COMPLETED,
             data: Optional[Dict] = None) -> bool:
        """Send notification via Apprise"""
        if not self.apprise:
            return False

        try:
            import apprise

            # Map priority
            priority_map = {
                NotificationPriority.LOW: apprise.NotifyType.INFO,
                NotificationPriority.NORMAL: apprise.NotifyType.SUCCESS,
                NotificationPriority.HIGH: apprise.NotifyType.WARNING,
                NotificationPriority.URGENT: apprise.NotifyType.FAILURE,
            }

            notify_type = priority_map.get(priority, apprise.NotifyType.INFO)

            # Override based on notification type
            if notification_type in [NotificationType.BACKUP_FAILED, NotificationType.SYSTEM_ERROR]:
                notify_type = apprise.NotifyType.FAILURE
            elif notification_type in [NotificationType.BACKUP_PARTIAL, NotificationType.SYSTEM_WARNING]:
                notify_type = apprise.NotifyType.WARNING
            elif notification_type == NotificationType.BACKUP_COMPLETED:
                notify_type = apprise.NotifyType.SUCCESS

            result = self.apprise.notify(
                body=message,
                title=title,
                notify_type=notify_type
            )

            if result:
                logger.info(f"Apprise notification sent to {len(self.urls)} service(s)")
                return True
            else:
                logger.error("Apprise notification failed")
                return False

        except Exception as e:
            logger.error('Failed to send Apprise notification: %s', type(e).__name__)
            return False
