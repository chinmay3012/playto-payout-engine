import uuid

from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.exceptions import ValidationError
from django.db import OperationalError

from .auth_utils import decode_token, issue_access_token, issue_refresh_token, login_merchant_user, register_merchant_user
from .exceptions import InsufficientBalanceError, RiskRuleViolationError
from .models import (
    ApiKey,
    BankAccount,
    IdempotencyKey,
    LedgerEntry,
    Merchant,
    MerchantRiskProfile,
    Payout,
    WebhookDeliveryAttempt,
    WebhookEndpoint,
)
from .serializers import (
    ApiKeyCreateSerializer,
    ApiKeySerializer,
    BankAccountSerializer,
    LedgerEntrySerializer,
    MerchantRiskProfileSerializer,
    MerchantUserLoginSerializer,
    MerchantUserRegisterSerializer,
    MerchantSerializer,
    PayoutDetailSerializer,
    PayoutRequestSerializer,
    PayoutSerializer,
    WebhookDeliveryAttemptSerializer,
    WebhookEndpointCreateSerializer,
    WebhookEndpointSerializer,
)
from .services import (
    authenticate_api_key,
    create_api_key,
    create_payout_request,
    create_webhook_endpoint,
    get_merchant_balance,
    has_any_role,
    is_admin_role,
    reserve_idempotency_key,
)
from .tasks import process_payout_task


def error_response(code: str, detail: str, http_status: int):
    return Response({'error': code, 'detail': detail}, status=http_status)


def require_api_scope(request, scope: str):
    raw_key = request.headers.get('X-API-Key')
    if not raw_key and getattr(settings, 'ALLOW_LEGACY_WRITE_WITHOUT_API_KEY', False):
        return None, None
    if not raw_key:
        return None, error_response(
            'UNAUTHORIZED',
            'X-API-Key header is required for this endpoint',
            status.HTTP_401_UNAUTHORIZED,
        )
    api_key = authenticate_api_key(raw_key, required_scope=scope)
    if not api_key:
        return None, error_response(
            'FORBIDDEN',
            f'Invalid API key or missing required scope: {scope}',
            status.HTTP_403_FORBIDDEN,
        )
    return api_key, None


def require_bearer_auth(request):
    auth_header = request.headers.get('Authorization', '')
    token = ''
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '', 1).strip()
    if not token:
        token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME, '')
    if not token:
        return None, error_response('UNAUTHORIZED', 'Authentication required', status.HTTP_401_UNAUTHORIZED)
    payload = decode_token(token, expected_type='access')
    if not payload:
        return None, error_response(
            'UNAUTHORIZED',
            'Invalid or expired token',
            status.HTTP_401_UNAUTHORIZED,
        )
    return payload, None


def attach_auth_cookies(response: Response, access_token: str, refresh_token: str) -> Response:
    response.set_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        access_token,
        max_age=settings.JWT_ACCESS_TOKEN_MINUTES * 60,
        httponly=True,
        secure=settings.JWT_COOKIE_SECURE,
        samesite=settings.JWT_COOKIE_SAMESITE,
        path='/',
    )
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=settings.JWT_REFRESH_TOKEN_MINUTES * 60,
        httponly=True,
        secure=settings.JWT_COOKIE_SECURE,
        samesite=settings.JWT_COOKIE_SAMESITE,
        path='/api/v1/auth/',
    )
    return response


def clear_auth_cookies(response: Response) -> Response:
    response.delete_cookie(settings.JWT_ACCESS_COOKIE_NAME, path='/')
    response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME, path='/api/v1/auth/')
    return response


class MerchantListView(APIView):
    def get(self, request):
        merchants = Merchant.objects.all().order_by('id')
        return Response(MerchantSerializer(merchants, many=True).data)


class MerchantBalanceView(APIView):
    def get(self, request, merchant_id):
        if not Merchant.objects.filter(id=merchant_id).exists():
            return error_response('MERCHANT_NOT_FOUND', 'Merchant not found', 404)

        balance = get_merchant_balance(merchant_id)
        payload = {
            'merchant_id': merchant_id,
            **balance,
        }
        return Response(payload)


class MerchantLedgerView(APIView):
    def get(self, request, merchant_id):
        if not Merchant.objects.filter(id=merchant_id).exists():
            return error_response('MERCHANT_NOT_FOUND', 'Merchant not found', 404)

        queryset = LedgerEntry.objects.filter(merchant_id=merchant_id).order_by('-created_at')
        page_size = 10
        try:
            page_num = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page_num = 1
        offset = (page_num - 1) * page_size
        total = queryset.count()
        page = queryset[offset : offset + page_size]

        next_page = None
        prev_page = None
        if offset + page_size < total:
            next_page = f'/api/v1/merchants/{merchant_id}/ledger/?page={page_num + 1}'
        if page_num > 1:
            prev_page = f'/api/v1/merchants/{merchant_id}/ledger/?page={page_num - 1}'

        return Response(
            {
                'count': total,
                'next': next_page,
                'previous': prev_page,
                'results': LedgerEntrySerializer(page, many=True).data,
            }
        )


class MerchantBankAccountsView(APIView):
    def get(self, request, merchant_id):
        if not Merchant.objects.filter(id=merchant_id).exists():
            return error_response('MERCHANT_NOT_FOUND', 'Merchant not found', 404)

        bank_accounts = BankAccount.objects.filter(
            merchant_id=merchant_id, is_active=True
        ).order_by('id')
        return Response(BankAccountSerializer(bank_accounts, many=True).data)


class PayoutCreateView(APIView):
    def post(self, request):
        api_key, err = require_api_scope(request, 'payouts:write')
        if err:
            return err

        raw_key = request.headers.get('Idempotency-Key')
        if not raw_key:
            return error_response(
                'INVALID_IDEMPOTENCY_KEY',
                'Idempotency-Key header is required',
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            key = uuid.UUID(raw_key)
        except ValueError:
            return error_response(
                'INVALID_IDEMPOTENCY_KEY',
                'Idempotency-Key must be a valid UUID',
                status.HTTP_400_BAD_REQUEST,
            )

        serializer = PayoutRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'INVALID_REQUEST',
                '; '.join([f'{k}: {v[0]}' for k, v in serializer.errors.items()]),
                status.HTTP_400_BAD_REQUEST,
            )

        merchant_id = serializer.validated_data['merchant_id']
        amount_paise = serializer.validated_data['amount_paise']
        bank_account_id = serializer.validated_data['bank_account_id']

        if api_key and merchant_id != api_key.merchant_id:
            return error_response(
                'FORBIDDEN',
                'API key cannot create payouts for another merchant',
                status.HTTP_403_FORBIDDEN,
            )

        if not Merchant.objects.filter(id=merchant_id).exists():
            return error_response('MERCHANT_NOT_FOUND', 'Merchant not found', 404)

        now = timezone.now()
        try:
            existing = IdempotencyKey.objects.filter(
                key=key,
                merchant_id=merchant_id,
                expires_at__gt=now,
            ).first()
        except OperationalError:
            return error_response(
                'TEMPORARY_LOCK',
                'Concurrent write contention. Please retry.',
                status.HTTP_409_CONFLICT,
            )

        if existing and existing.response_body is not None:
            return Response(existing.response_body, status=200)
        if existing and existing.response_body is None:
            return error_response(
                'KEY_IN_FLIGHT',
                'A request with this Idempotency-Key is currently being processed. Retry after a moment.',
                status.HTTP_409_CONFLICT,
            )

        try:
            key_record, created = reserve_idempotency_key(merchant_id, key)
        except OperationalError:
            return error_response(
                'TEMPORARY_LOCK',
                'Concurrent write contention. Please retry.',
                status.HTTP_409_CONFLICT,
            )
        if not created and key_record.response_body is not None:
            return Response(key_record.response_body, status=200)
        if not created and key_record.response_body is None:
            return error_response(
                'KEY_IN_FLIGHT',
                'A request with this Idempotency-Key is currently being processed. Retry after a moment.',
                status.HTTP_409_CONFLICT,
            )

        try:
            payout = create_payout_request(
                merchant_id=merchant_id,
                amount_paise=amount_paise,
                bank_account_id=bank_account_id,
                idempotency_key=key,
            )
            response_body = PayoutSerializer(payout).data
            response_status = status.HTTP_201_CREATED
        except Merchant.DoesNotExist:
            response_body = {'error': 'MERCHANT_NOT_FOUND', 'detail': 'Merchant not found'}
            response_status = status.HTTP_404_NOT_FOUND
        except BankAccount.DoesNotExist:
            response_body = {
                'error': 'BANK_ACCOUNT_NOT_FOUND',
                'detail': 'Bank account not found or not owned by merchant',
            }
            response_status = status.HTTP_404_NOT_FOUND
        except InsufficientBalanceError as exc:
            response_body = {
                'error': 'INSUFFICIENT_BALANCE',
                'detail': str(exc),
            }
            response_status = status.HTTP_402_PAYMENT_REQUIRED
        except RiskRuleViolationError as exc:
            response_body = {
                'error': 'RISK_RULE_VIOLATION',
                'detail': exc.detail,
            }
            response_status = status.HTTP_429_TOO_MANY_REQUESTS
        except ValidationError as exc:
            response_body = {
                'error': 'INVALID_REQUEST',
                'detail': str(exc),
            }
            response_status = status.HTTP_400_BAD_REQUEST
        except OperationalError:
            response_body = {
                'error': 'TEMPORARY_LOCK',
                'detail': 'Concurrent write contention. Please retry.',
            }
            response_status = status.HTTP_409_CONFLICT
        except Exception:
            try:
                key_record.delete()
            except Exception:
                pass
            raise

        key_record.response_body = response_body
        key_record.response_status = response_status
        try:
            key_record.save(update_fields=['response_body', 'response_status'])
        except OperationalError:
            return error_response(
                'TEMPORARY_LOCK',
                'Concurrent write contention. Please retry.',
                status.HTTP_409_CONFLICT,
            )

        if response_status == status.HTTP_201_CREATED:
            try:
                process_payout_task.delay(response_body['id'])
            except Exception:
                # Fallback for local env when broker enqueue fails.
                process_payout_task(response_body['id'])

        return Response(response_body, status=response_status)


class PayoutDetailView(APIView):
    def get(self, request, payout_id):
        try:
            payout = Payout.objects.select_related('bank_account').get(id=payout_id)
        except Payout.DoesNotExist:
            return error_response('INVALID_REQUEST', 'Payout not found', 404)

        return Response(PayoutDetailSerializer(payout).data)


class MerchantPayoutsView(APIView):
    def get(self, request, merchant_id):
        if not Merchant.objects.filter(id=merchant_id).exists():
            return error_response('MERCHANT_NOT_FOUND', 'Merchant not found', 404)

        queryset = Payout.objects.filter(merchant_id=merchant_id).order_by('-created_at')
        page_size = 10
        try:
            page_num = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page_num = 1
        offset = (page_num - 1) * page_size
        total = queryset.count()
        page = queryset[offset : offset + page_size]

        next_page = None
        prev_page = None
        if offset + page_size < total:
            next_page = f'/api/v1/merchants/{merchant_id}/payouts/?page={page_num + 1}'
        if page_num > 1:
            prev_page = f'/api/v1/merchants/{merchant_id}/payouts/?page={page_num - 1}'

        return Response(
            {
                'count': total,
                'next': next_page,
                'previous': prev_page,
                'results': PayoutSerializer(page, many=True).data,
            }
        )


class ApiKeyView(APIView):
    def get(self, request):
        merchant_id = request.query_params.get('merchant_id')
        qs = ApiKey.objects.all().order_by('-created_at')
        if merchant_id:
            qs = qs.filter(merchant_id=merchant_id)
        return Response(ApiKeySerializer(qs, many=True).data)

    def post(self, request):
        serializer = ApiKeyCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'INVALID_REQUEST',
                '; '.join([f'{k}: {v[0]}' for k, v in serializer.errors.items()]),
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            api_key, raw_key = create_api_key(**serializer.validated_data)
        except Merchant.DoesNotExist:
            return error_response('MERCHANT_NOT_FOUND', 'Merchant not found', 404)
        payload = ApiKeySerializer(api_key).data
        payload['raw_key'] = raw_key
        return Response(payload, status=status.HTTP_201_CREATED)


class WebhookEndpointView(APIView):
    def get(self, request):
        merchant_id = request.query_params.get('merchant_id')
        qs = WebhookEndpoint.objects.filter(is_active=True).order_by('-created_at')
        if merchant_id:
            qs = qs.filter(merchant_id=merchant_id)
        return Response(WebhookEndpointSerializer(qs, many=True).data)

    def post(self, request):
        serializer = WebhookEndpointCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'INVALID_REQUEST',
                '; '.join([f'{k}: {v[0]}' for k, v in serializer.errors.items()]),
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            endpoint = create_webhook_endpoint(**serializer.validated_data)
        except Merchant.DoesNotExist:
            return error_response('MERCHANT_NOT_FOUND', 'Merchant not found', 404)
        payload = WebhookEndpointSerializer(endpoint).data
        payload['secret'] = endpoint.secret
        return Response(payload, status=status.HTTP_201_CREATED)


class AuthRegisterView(APIView):
    def post(self, request):
        serializer = MerchantUserRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                'INVALID_REQUEST',
                '; '.join([f'{k}: {v[0]}' for k, v in serializer.errors.items()]),
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            profile = register_merchant_user(**serializer.validated_data)
        except Merchant.DoesNotExist:
            return error_response('MERCHANT_NOT_FOUND', 'Merchant not found', 404)
        except Exception as exc:
            return error_response('INVALID_REQUEST', str(exc), 400)
        return Response(
            {
                'id': profile.id,
                'merchant_id': profile.merchant_id,
                'username': profile.user.username,
                'email': profile.user.email,
                'role': profile.role,
            },
            status=status.HTTP_201_CREATED,
        )


class AuthLoginView(APIView):
    def post(self, request):
        serializer = MerchantUserLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response('INVALID_REQUEST', 'Invalid login payload', 400)
        lock_key = f"auth-login-lock:{serializer.validated_data['username']}"
        failed_attempts = cache.get(lock_key, 0)
        if failed_attempts >= 5:
            return error_response('TOO_MANY_ATTEMPTS', 'Too many failed login attempts', 429)
        result = login_merchant_user(**serializer.validated_data)
        if not result:
            cache.set(lock_key, failed_attempts + 1, timeout=900)
            return error_response('UNAUTHORIZED', 'Invalid credentials', 401)
        cache.delete(lock_key)
        profile, access_token, refresh_token = result
        response = Response(
            {
                'merchant_id': profile.merchant_id,
                'role': profile.role,
                'username': profile.user.username,
            }
        )
        return attach_auth_cookies(response, access_token, refresh_token)


class AuthRefreshView(APIView):
    def post(self, request):
        refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME, '')
        payload = decode_token(refresh_token, expected_type='refresh')
        if not payload:
            return error_response('UNAUTHORIZED', 'Invalid refresh token', 401)
        access_token = issue_access_token(
            user_id=int(payload['sub']),
            merchant_id=payload['merchant_id'],
            role=payload['role'],
        )
        rotated_refresh = issue_refresh_token(
            user_id=int(payload['sub']),
            merchant_id=payload['merchant_id'],
            role=payload['role'],
        )
        response = Response({'ok': True})
        return attach_auth_cookies(response, access_token, rotated_refresh)


class AuthLogoutView(APIView):
    def post(self, request):
        return clear_auth_cookies(Response({'ok': True}))


class AuthMeView(APIView):
    def get(self, request):
        payload, err = require_bearer_auth(request)
        if err:
            return err
        user = User.objects.filter(id=int(payload['sub'])).first()
        if not user:
            return error_response('UNAUTHORIZED', 'User not found', 401)
        return Response(
            {
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'merchant_id': payload['merchant_id'],
                'role': payload['role'],
            }
        )


class MerchantRiskProfileView(APIView):
    def get(self, request, merchant_id):
        payload, err = require_bearer_auth(request)
        if err:
            return err
        if payload['merchant_id'] != merchant_id:
            return error_response('FORBIDDEN', 'Token merchant mismatch', 403)

        profile, _ = MerchantRiskProfile.objects.get_or_create(merchant_id=merchant_id)
        return Response(MerchantRiskProfileSerializer(profile).data)

    def patch(self, request, merchant_id):
        payload, err = require_bearer_auth(request)
        if err:
            return err
        if payload['merchant_id'] != merchant_id:
            return error_response('FORBIDDEN', 'Token merchant mismatch', 403)
        if not is_admin_role(payload.get('role', '')):
            return error_response('FORBIDDEN', 'Role not allowed to update risk profile', 403)

        profile, _ = MerchantRiskProfile.objects.get_or_create(merchant_id=merchant_id)
        serializer = MerchantRiskProfileSerializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                'INVALID_REQUEST',
                '; '.join([f'{k}: {v[0]}' for k, v in serializer.errors.items()]),
                400,
            )
        serializer.save()
        return Response(serializer.data)


class MerchantWebhookDeliveriesView(APIView):
    def get(self, request, merchant_id):
        payload, err = require_bearer_auth(request)
        if err:
            return err
        if payload['merchant_id'] != merchant_id:
            return error_response('FORBIDDEN', 'Token merchant mismatch', 403)

        attempts = (
            WebhookDeliveryAttempt.objects.filter(event__merchant_id=merchant_id)
            .select_related('event', 'endpoint')
            .order_by('-created_at')[:50]
        )
        return Response(WebhookDeliveryAttemptSerializer(attempts, many=True).data)


class AccountProfileView(APIView):
    def patch(self, request):
        payload, err = require_bearer_auth(request)
        if err:
            return err
        user = User.objects.filter(id=int(payload['sub'])).first()
        if not user:
            return error_response('UNAUTHORIZED', 'User not found', 401)
        username = request.data.get('username')
        email = request.data.get('email')
        if username:
            user.username = username
        if email:
            user.email = email
        user.save(update_fields=['username', 'email'])
        return Response({'username': user.username, 'email': user.email})


class AccountChangePasswordView(APIView):
    def post(self, request):
        payload, err = require_bearer_auth(request)
        if err:
            return err
        current_password = request.data.get('current_password', '')
        new_password = request.data.get('new_password', '')
        user = User.objects.filter(id=int(payload['sub'])).first()
        if not user:
            return error_response('UNAUTHORIZED', 'User not found', 401)
        if not user.check_password(current_password):
            return error_response('INVALID_REQUEST', 'Current password is incorrect', 400)
        if len(new_password) < 8:
            return error_response('INVALID_REQUEST', 'New password must be at least 8 characters', 400)
        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'ok': True})


class OperatorHomeView(APIView):
    def get(self, request):
        payload, err = require_bearer_auth(request)
        if err:
            return err
        if not has_any_role(payload.get('role', ''), {'OPERATOR', 'ADMIN', 'OWNER'}):
            return error_response('FORBIDDEN', 'Operator access required', 403)
        return Response({'section': 'operator', 'ok': True})


class AdminHomeView(APIView):
    def get(self, request):
        payload, err = require_bearer_auth(request)
        if err:
            return err
        if not is_admin_role(payload.get('role', '')):
            return error_response('FORBIDDEN', 'Admin access required', 403)
        return Response({'section': 'admin', 'ok': True})
