"""
Authentication API
"""
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
import jwt
import hashlib
import re
import secrets
from functools import wraps

from app import db, limiter, _app_init_lock
from app.models.backup import Setting, User
from app.config import Config
from app.time_utils import utc_now_naive

auth_bp = Blueprint('auth', __name__)


def validate_password(password):
    """Accept any non-empty, UTF-8-encodable password without composition rules."""
    if not isinstance(password, str) or not password:
        return False, "Password cannot be empty"
    try:
        password.encode('utf-8')
    except UnicodeEncodeError:
        return False, "Password contains invalid Unicode"
    return True, None


def token_required(f):
    """Decorator for protected routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization'].strip()
            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != 'bearer':
                return jsonify({'error': 'Invalid token format'}), 401
            token = parts[1]

        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            data = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
            current_user = User.query.filter_by(id=data['user_id']).first()
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
            expected_fingerprint = _password_fingerprint(current_user.password_hash)
            if not secrets.compare_digest(data.get('pwd', ''), expected_fingerprint):
                return jsonify({'error': 'Token is no longer valid'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except (KeyError, TypeError, jwt.InvalidTokenError):
            return jsonify({'error': 'Invalid token'}), 401

        return f(current_user, *args, **kwargs)

    return decorated


def _password_fingerprint(password_hash):
    """Bind tokens to the current password hash without exposing that hash."""
    return hashlib.sha256(password_hash.encode('utf-8')).hexdigest()[:24]


def _issue_token(user, *, expires_in=None, token_kind='access'):
    lifetime = expires_in or Config.JWT_ACCESS_TOKEN_EXPIRES
    now = datetime.now(timezone.utc)
    return jwt.encode({
        'user_id': user.id,
        'username': user.username,
        'pwd': _password_fingerprint(user.password_hash),
        'kind': token_kind,
        'iat': now,
        'exp': now + lifetime,
    }, Config.JWT_SECRET_KEY, algorithm='HS256')


def is_admin_user(user):
    """The first account is the owner/admin in the schema-free role model."""
    first_id = db.session.query(db.func.min(User.id)).scalar()
    if first_id is not None and user.id == first_id:
        return True
    return Setting.get(f'user.role.{user.id}', 'viewer') == 'admin'


def admin_required(f):
    """Require the authenticated owner account for mutating admin actions."""
    @token_required
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if not is_admin_user(current_user):
            return jsonify({'error': 'Administrator access required'}), 403
        return f(current_user, *args, **kwargs)

    return decorated


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")  # Rate limiting: max 5 login attempts per minute
def login():
    """User login with rate limiting"""
    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify({'error': 'Missing username or password'}), 400
    username = data.get('username')
    password = data.get('password')
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({'error': 'Missing username or password'}), 400
    if not validate_password(password)[0]:
        return jsonify({'error': 'Invalid credentials'}), 401

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401

    # Update last login
    user.last_login = utc_now_naive()
    db.session.commit()

    # Generate token
    token = _issue_token(user)

    return jsonify({
        'access_token': token,
        'token_type': 'Bearer',
        'expires_in': int(Config.JWT_ACCESS_TOKEN_EXPIRES.total_seconds()),
        'user': user.to_dict()
    }), 200


@auth_bp.route('/api-token', methods=['POST'])
@admin_required
@limiter.limit("3 per hour")
def create_api_token(current_user):
    """Create a password-bound automation token with a bounded lifetime."""
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({'error': 'Current password is required'}), 400

    current_password = data.get('current_password')
    if not validate_password(current_password)[0] or not check_password_hash(
        current_user.password_hash, current_password
    ):
        return jsonify({'error': 'Current password is incorrect'}), 403

    expires_days = data.get('expires_days', 365)
    if isinstance(expires_days, bool):
        return jsonify({'error': 'expires_days must be between 1 and 365'}), 400
    try:
        expires_days = int(expires_days)
    except (TypeError, ValueError):
        return jsonify({'error': 'expires_days must be between 1 and 365'}), 400
    if not 1 <= expires_days <= 365:
        return jsonify({'error': 'expires_days must be between 1 and 365'}), 400

    lifetime = timedelta(days=expires_days)
    token = _issue_token(
        current_user,
        expires_in=lifetime,
        token_kind='automation',
    )
    return jsonify({
        'access_token': token,
        'token_type': 'Bearer',
        'expires_in': int(lifetime.total_seconds()),
        'warning': 'Changing the account password revokes this token.',
    }), 201


@auth_bp.route('/register', methods=['POST'])
@admin_required
@limiter.limit("3 per hour")
def register(current_user):
    """User registration (admin only, rate limited)"""
    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify({'error': 'Missing username or password'}), 400
    raw_username = data.get('username')
    if not isinstance(raw_username, str) or not isinstance(data.get('password'), str):
        return jsonify({'error': 'Missing username or password'}), 400
    username = raw_username.strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,80}', username):
        return jsonify({'error': 'Invalid username'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400

    role = data.get('role', 'viewer')
    if role not in ('viewer', 'admin'):
        return jsonify({'error': 'Role must be viewer or admin'}), 400

    # Validate password strength
    is_valid, error_msg = validate_password(data['password'])
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    password_hash = generate_password_hash(data['password'])
    new_user = User(username=username, password_hash=password_hash)

    db.session.add(new_user)
    db.session.flush()
    db.session.add(Setting(key=f'user.role.{new_user.id}', value=role))
    db.session.commit()

    user_data = new_user.to_dict()
    user_data['role'] = role
    return jsonify({
        'message': 'User created successfully',
        'user': user_data
    }), 201


@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user(current_user):
    """Get current user information"""
    response = current_user.to_dict()
    response['is_admin'] = is_admin_user(current_user)
    response['role'] = 'admin' if response['is_admin'] else 'viewer'
    return jsonify(response), 200


@auth_bp.route('/password', methods=['PUT'])
@token_required
def change_password(current_user):
    """Change user password"""
    data = request.get_json()

    if not data or not data.get('current_password') or not data.get('new_password'):
        return jsonify({'error': 'Current and new password are required'}), 400

    if not validate_password(data['current_password'])[0] or not check_password_hash(
        current_user.password_hash, data['current_password']
    ):
        return jsonify({'error': 'Current password is incorrect'}), 403

    # Validate password strength
    is_valid, error_msg = validate_password(data['new_password'])
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    # Update password
    current_user.password_hash = generate_password_hash(data['new_password'])
    db.session.commit()

    return jsonify({
        'message': 'Password changed successfully',
        'access_token': _issue_token(current_user),
    }), 200


@auth_bp.route('/setup/status', methods=['GET'])
@limiter.limit("30 per minute")
def setup_status():
    """Expose only whether first-run setup is required."""
    return jsonify({'needs_setup': db.session.query(User.id).first() is None}), 200


@auth_bp.route('/setup', methods=['POST'])
@limiter.limit("5 per minute")
def setup_owner():
    """Create the first owner only while the database has no accounts."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid setup request'}), 400
    username = data.get('username')
    password = data.get('password')
    confirmation = data.get('confirm_password')
    if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,80}', username):
        return jsonify({'error': 'Invalid username'}), 400
    valid, error = validate_password(password)
    if not valid:
        return jsonify({'error': error}), 400
    if not isinstance(confirmation, str) or not validate_password(confirmation)[0]:
        return jsonify({'error': 'Passwords do not match'}), 400
    if not secrets.compare_digest(password.encode('utf-8'), confirmation.encode('utf-8')):
        return jsonify({'error': 'Passwords do not match'}), 400

    with _app_init_lock(Config):
        if db.session.query(User.id).first() is not None:
            return jsonify({'error': 'Setup already completed'}), 409
        owner = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(owner)
        db.session.commit()
        return jsonify({'message': 'Owner created'}), 201


@auth_bp.route('/init', methods=['POST'])
@limiter.limit("3 per hour")
def init_admin():
    """Legacy initialization never accepts remote account creation."""
    return jsonify({'error': 'Use first-run setup'}), 403
