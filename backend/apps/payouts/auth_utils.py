from datetime import datetime, timedelta, timezone
import secrets
import jwt

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User

from .models import Merchant, MerchantUser


def _issue_token(*, user_id: int, merchant_id: int, role: str, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user_id),
        'merchant_id': merchant_id,
        'role': role,
        'type': token_type,
        'jti': secrets.token_urlsafe(16),
        'iat': int(now.timestamp()),
        'exp': int((now + lifetime).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')


def issue_access_token(*, user_id: int, merchant_id: int, role: str) -> str:
    return _issue_token(
        user_id=user_id,
        merchant_id=merchant_id,
        role=role,
        token_type='access',
        lifetime=timedelta(minutes=settings.JWT_ACCESS_TOKEN_MINUTES),
    )


def issue_refresh_token(*, user_id: int, merchant_id: int, role: str) -> str:
    return _issue_token(
        user_id=user_id,
        merchant_id=merchant_id,
        role=role,
        token_type='refresh',
        lifetime=timedelta(minutes=settings.JWT_REFRESH_TOKEN_MINUTES),
    )


def decode_token(token: str, expected_type: str | None = None) -> dict | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=['HS256'])
        if expected_type and payload.get('type') != expected_type:
            return None
        return payload
    except jwt.PyJWTError:
        return None


def register_merchant_user(
    *,
    merchant_id: int,
    username: str,
    email: str,
    password: str,
    role: str = MerchantUser.Role.OPERATOR,
) -> MerchantUser:
    merchant = Merchant.objects.get(id=merchant_id)
    user = User.objects.create_user(username=username, email=email, password=password)
    return MerchantUser.objects.create(user=user, merchant=merchant, role=role)


def login_merchant_user(*, username: str, password: str) -> tuple[MerchantUser, str, str] | None:
    user = authenticate(username=username, password=password)
    if not user:
        return None
    profile = MerchantUser.objects.filter(user=user, is_active=True).first()
    if not profile:
        return None
    access_token = issue_access_token(
        user_id=user.id,
        merchant_id=profile.merchant_id,
        role=profile.role,
    )
    refresh_token = issue_refresh_token(
        user_id=user.id,
        merchant_id=profile.merchant_id,
        role=profile.role,
    )
    return profile, access_token, refresh_token
