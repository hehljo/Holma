"""
Holma - Automated Multi-Source Backup Manager
Main Application Module
"""
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_babel import Babel
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from sqlalchemy import text
from contextlib import contextmanager
import fcntl
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from werkzeug.middleware.proxy_fix import ProxyFix
from app.config import Config
from app.version import APP_VERSION

db = SQLAlchemy()
babel = Babel()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


@contextmanager
def _app_init_lock(config_class):
    """Serialize schema/bootstrap work across gunicorn and worker processes."""
    lock_path = config_class.APP_INIT_LOCK_PATH
    parent = os.path.dirname(lock_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(lock_path, 'a+', encoding='utf-8') as lock_file:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def get_locale():
    """Get locale from request header or default to English"""
    return request.headers.get('Accept-Language', 'en').split(',')[0][:2]


def _configure_file_logging(config_class):
    """Configure or refresh the process logger from persisted settings."""
    from app.runtime_settings import get_setting

    root_logger = logging.getLogger()
    log_file = config_class.LOG_FILE
    log_dir = os.path.dirname(log_file)
    if not os.path.isdir(log_dir):
        return

    try:
        retention = max(
            1,
            int(get_setting(
                'log_retention_days', config_class.LOG_RETENTION_DAYS
            )),
        )
    except (TypeError, ValueError):
        retention = max(1, int(config_class.LOG_RETENTION_DAYS))
        root_logger.warning('Ignoring invalid stored log_retention_days')
    level = getattr(logging, config_class.LOG_LEVEL, logging.INFO)
    file_handler = next(
        (
            handler for handler in root_logger.handlers
            if isinstance(handler, TimedRotatingFileHandler)
            and os.path.abspath(handler.baseFilename) == os.path.abspath(log_file)
        ),
        None,
    )
    if file_handler is None:
        file_handler = TimedRotatingFileHandler(
            log_file,
            when='midnight',
            interval=1,
            backupCount=retention,
            utc=True,
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s [%(name)s] %(message)s'
        ))
        root_logger.addHandler(file_handler)
    else:
        file_handler.backupCount = retention
    file_handler.setLevel(level)
    root_logger.setLevel(level)


def create_app(config_class=Config):
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    if config_class.TRUST_PROXY_HEADERS:
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1
        )

    # Validate critical security settings
    config_class.validate()

    # Babel configuration
    app.config['BABEL_DEFAULT_LOCALE'] = 'en'
    app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'de']
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

    # Initialize extensions
    db.init_app(app)
    babel.init_app(app, locale_selector=get_locale)
    limiter.init_app(app)

    # CORS Configuration - Restrict to allowed origins
    allowed_origins = os.environ.get('ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
    CORS(app, resources={
        r"/api/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "Accept-Language"],
            "expose_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
            "max_age": 3600
        }
    })

    # Security Headers (disabled force_https for development, enable in production behind proxy)
    csp = {
        'default-src': "'self'",
        'script-src': ["'self'"],
        'style-src': ["'self'", "'unsafe-inline'"],
        'img-src': ["'self'", "data:", "https:"],
        'font-src': ["'self'", "data:"],
        'connect-src': ["'self'"],
    }
    Talisman(app,
        force_https=config_class.FORCE_HTTPS,
        strict_transport_security=config_class.FORCE_HTTPS,
        content_security_policy=csp,
    )

    # Register blueprints
    from app.api.backup import backup_bp
    from app.api.sources import sources_bp
    from app.api.auth import auth_bp
    from app.api.notifications import notifications_bp
    from app.api.settings import settings_bp
    from app.api.config import config_bp

    app.register_blueprint(backup_bp, url_prefix='/api/v1/backup')
    app.register_blueprint(sources_bp, url_prefix='/api/v1/sources')
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(notifications_bp, url_prefix='/api/v1/notifications')
    app.register_blueprint(settings_bp, url_prefix='/api/v1/settings')
    app.register_blueprint(config_bp, url_prefix='/api/v1/config')

    # Create database tables if they don't exist
    with app.app_context():
        with _app_init_lock(config_class):
            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(db.engine)
            existing_tables = set(inspector.get_table_names())
            # Only create tables that don't exist yet. The process lock avoids
            # SQLite's check-then-create race during multi-worker startup.
            tables_to_create = [
                table for table in db.metadata.sorted_tables
                if table.name not in existing_tables
            ]
            if tables_to_create:
                db.metadata.create_all(db.engine, tables=tables_to_create)
                app.logger.info(
                    "Created new tables: %s",
                    [table.name for table in tables_to_create],
                )

            # Bootstrap admin user if no users exist
            from app.models.backup import User
            from werkzeug.security import generate_password_hash
            from sqlalchemy.exc import IntegrityError

            try:
                if User.query.count() == 0:
                    import secrets
                    configured_password = os.environ.get('DEFAULT_ADMIN_PASSWORD')
                    default_password = configured_password or secrets.token_urlsafe(18)
                    admin = User(
                        username='admin',
                        password_hash=generate_password_hash(default_password)
                    )
                    db.session.add(admin)
                    db.session.commit()
                    if configured_password:
                        print("[INIT] Admin user created with configured password.")
                    else:
                        print(f"[INIT] Admin user created. Password: {default_password}")
                    app.logger.info(
                        "Bootstrap: Admin user created. Check container stdout for password."
                    )
            except IntegrityError:
                db.session.rollback()
                app.logger.info("Bootstrap: Admin user already exists, skipping creation")

            # One-time, atomic migration of legacy plaintext source credentials.
            from app.source_config import migrate_source_secrets
            migrate_source_secrets()
            from app.notification_config import migrate_notification_secrets
            migrate_notification_secrets(
                os.environ.get(
                    'NOTIFICATION_CONFIG_PATH', '/app/config/notifications.json'
                )
            )
            _configure_file_logging(config_class)

    @app.route('/health')
    @limiter.exempt  # Exclude health check from rate limiting
    def health():
        """Enhanced health check with database connectivity test"""
        try:
            # Test database connection
            db.session.execute(text('SELECT 1'))
            db_status = 'ok'
        except Exception as e:
            db_status = f'error: {str(e)}'
            return jsonify({
                'status': 'unhealthy',
                'version': APP_VERSION,
                'database': db_status
            }), 503

        return jsonify({
            'status': 'healthy',
            'version': APP_VERSION,
            'database': db_status
        }), 200

    return app
