from datetime import timedelta
import hashlib
import hmac
import json
from urllib import request as urlrequest

from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from .exceptions import InsufficientBalanceError, InvalidTransitionError, RiskRuleViolationError
from .models import (
    ApiKey,
    BankAccount,
    EntryType,
    EventOutbox,
    IdempotencyKey,
    LedgerEntry,
    Merchant,
    Payout,
    PayoutStatus,
    WebhookDeliveryAttempt,
    WebhookEndpoint,
)

ALLOWED_TRANSITIONS = {
    PayoutStatus.PENDING: [PayoutStatus.PROCESSING],
    PayoutStatus.PROCESSING: [PayoutStatus.COMPLETED, PayoutStatus.FAILED],
    PayoutStatus.COMPLETED: [],
    PayoutStatus.FAILED: [],
}

ROLE_ADMIN = 'ADMIN'
ROLE_OWNER = 'OWNER'
ROLE_OPERATOR = 'OPERATOR'
ROLE_USER = 'USER'


def is_admin_role(role: str) -> bool:
    return role in {ROLE_OWNER, ROLE_ADMIN}


def has_any_role(role: str, allowed_roles: set[str]) -> bool:
    return role in allowed_roles


def paise_to_inr_str(paise: int) -> str:
    return f'{paise / 100:.2f}'


def get_merchant_balance(merchant_id: int) -> dict:
    result = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
        total_credits=Sum('amount_paise', filter=Q(entry_type=EntryType.CREDIT)),
        total_debits=Sum('amount_paise', filter=Q(entry_type=EntryType.DEBIT)),
    )
    total_credits = result['total_credits'] or 0
    total_debits = result['total_debits'] or 0
    total_paise = total_credits - total_debits

    held_paise = (
        Payout.objects.filter(
            merchant_id=merchant_id,
            status__in=[PayoutStatus.PENDING, PayoutStatus.PROCESSING],
        ).aggregate(held=Sum('amount_paise'))['held']
        or 0
    )

    # Important: DEBIT is recorded at payout creation time, so total_paise already
    # includes in-flight deductions. held_paise is display-only; available equals total.
    available_paise = total_paise

    return {
        'total_paise': total_paise,
        'held_paise': held_paise,
        'available_paise': available_paise,
        'total_inr': paise_to_inr_str(total_paise),
        'held_inr': paise_to_inr_str(held_paise),
        'available_inr': paise_to_inr_str(available_paise),
    }


def create_payout_request(
    merchant_id: int,
    amount_paise: int,
    bank_account_id: int,
    idempotency_key,
) -> Payout:
    with transaction.atomic():
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)
        bank_account = BankAccount.objects.get(
            id=bank_account_id, merchant_id=merchant_id, is_active=True
        )
        _enforce_payout_risk_limits(merchant_id=merchant.id, amount_paise=amount_paise)

        balance = get_merchant_balance(merchant.id)
        if balance['available_paise'] < amount_paise:
            raise InsufficientBalanceError(balance['available_paise'], amount_paise)

        payout = Payout.objects.create(
            merchant=merchant,
            bank_account=bank_account,
            amount_paise=amount_paise,
            status=PayoutStatus.PENDING,
            idempotency_key=idempotency_key,
        )

        LedgerEntry.objects.create(
            merchant=merchant,
            amount_paise=amount_paise,
            entry_type=EntryType.DEBIT,
            description=f'Payout #{payout.id} initiated',
            reference_id=str(payout.id),
        )
        _enqueue_payout_event(
            merchant_id=merchant.id,
            event_type='payout.pending',
            payout=payout,
        )

        return payout


def transition_payout_status(payout_id: int, new_status: str) -> Payout:
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)
        current_status = payout.status

        if new_status not in ALLOWED_TRANSITIONS.get(current_status, []):
            raise InvalidTransitionError(current_status, new_status)

        update_fields = {'status': new_status}
        if new_status == PayoutStatus.PROCESSING:
            update_fields['processing_started_at'] = timezone.now()

        updated_count = Payout.objects.filter(
            id=payout_id, status=current_status
        ).update(**update_fields)

        if updated_count == 0:
            raise InvalidTransitionError(current_status, new_status)

        payout.refresh_from_db()
        if new_status == PayoutStatus.PROCESSING:
            _enqueue_payout_event(
                merchant_id=payout.merchant_id,
                event_type='payout.processing',
                payout=payout,
            )
        elif new_status == PayoutStatus.COMPLETED:
            _enqueue_payout_event(
                merchant_id=payout.merchant_id,
                event_type='payout.completed',
                payout=payout,
            )
        return payout


def fail_payout_and_return_funds(payout_id: int):
    with transaction.atomic():
        payout = transition_payout_status(payout_id, PayoutStatus.FAILED)
        LedgerEntry.objects.create(
            merchant=payout.merchant,
            amount_paise=payout.amount_paise,
            entry_type=EntryType.CREDIT,
            description=f'Payout #{payout.id} failed - funds returned',
            reference_id=str(payout.id),
        )
        _enqueue_payout_event(
            merchant_id=payout.merchant_id,
            event_type='payout.failed',
            payout=payout,
        )


def reserve_idempotency_key(merchant_id: int, key):
    now = timezone.now()
    return IdempotencyKey.objects.get_or_create(
        key=key,
        merchant_id=merchant_id,
        defaults={
            'response_body': None,
            'response_status': None,
            'expires_at': now + timedelta(hours=24),
        },
    )


def mark_payout_for_retry(payout_id: int):
    return Payout.objects.filter(id=payout_id, status=PayoutStatus.PROCESSING).update(
        status=PayoutStatus.PENDING,
        attempt_count=F('attempt_count') + 1,
        processing_started_at=None,
    )


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def create_api_key(
    *,
    merchant_id: int,
    name: str,
    scopes: list[str],
    expires_in_days: int | None = None,
) -> tuple[ApiKey, str]:
    merchant = Merchant.objects.get(id=merchant_id)
    raw_key = ApiKey.generate_raw_key()
    hashed_key = hash_api_key(raw_key)
    expires_at = None
    if expires_in_days:
        expires_at = timezone.now() + timedelta(days=expires_in_days)

    api_key = ApiKey.objects.create(
        merchant=merchant,
        name=name,
        key_prefix=raw_key[:12],
        hashed_key=hashed_key,
        scopes=scopes,
        expires_at=expires_at,
    )
    return api_key, raw_key


def authenticate_api_key(raw_key: str, required_scope: str | None = None) -> ApiKey | None:
    hashed_key = hash_api_key(raw_key)
    api_key = ApiKey.objects.filter(hashed_key=hashed_key, is_active=True).first()
    if not api_key:
        return None
    if api_key.is_expired():
        return None
    if required_scope and required_scope not in (api_key.scopes or []):
        return None

    ApiKey.objects.filter(id=api_key.id).update(last_used_at=timezone.now())
    return api_key


def create_webhook_endpoint(merchant_id: int, url: str) -> WebhookEndpoint:
    merchant = Merchant.objects.get(id=merchant_id)
    secret = f"whsec_{ApiKey.generate_raw_key().replace('pk_live_', '')}"
    return WebhookEndpoint.objects.create(merchant=merchant, url=url, secret=secret)


def dispatch_pending_events(batch_size: int = 50) -> int:
    now = timezone.now()
    pending = EventOutbox.objects.filter(
        status='PENDING'
    ).filter(
        Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)
    ).order_by('id')[:batch_size]
    count = 0
    for event in pending:
        EventOutbox.objects.filter(id=event.id, status='PENDING').update(status='PROCESSING')
        endpoints = WebhookEndpoint.objects.filter(merchant_id=event.merchant_id, is_active=True)
        had_failure = False
        last_error = ''
        for endpoint in endpoints:
            delivery_success, delivery_error = _deliver_webhook_event(event, endpoint)
            if not delivery_success:
                had_failure = True
                last_error = delivery_error
        if had_failure:
            retry_count = event.retry_count + 1
            if retry_count >= 5:
                EventOutbox.objects.filter(id=event.id).update(
                    status='FAILED',
                    retry_count=retry_count,
                    last_error=last_error[:2000],
                )
            else:
                delay_seconds = 2 ** retry_count
                EventOutbox.objects.filter(id=event.id).update(
                    status='PENDING',
                    retry_count=retry_count,
                    next_attempt_at=timezone.now() + timedelta(seconds=delay_seconds),
                    last_error=last_error[:2000],
                )
        else:
            EventOutbox.objects.filter(id=event.id).update(
                status='DISPATCHED', dispatched_at=timezone.now(), last_error=''
            )
        count += 1
    return count


def _enqueue_payout_event(*, merchant_id: int, event_type: str, payout: Payout) -> None:
    EventOutbox.objects.create(
        merchant_id=merchant_id,
        event_type=event_type,
        payload={
            'payout_id': payout.id,
            'merchant_id': payout.merchant_id,
            'amount_paise': payout.amount_paise,
            'status': payout.status,
            'attempt_count': payout.attempt_count,
            'created_at': payout.created_at.isoformat() if payout.created_at else None,
            'updated_at': payout.updated_at.isoformat() if payout.updated_at else None,
        },
    )


def _deliver_webhook_event(event: EventOutbox, endpoint: WebhookEndpoint) -> tuple[bool, str]:
    payload_text = json.dumps(
        {'type': event.event_type, 'merchant_id': event.merchant_id, 'data': event.payload}
    )
    signature = hmac.new(endpoint.secret.encode(), payload_text.encode(), hashlib.sha256).hexdigest()
    req = urlrequest.Request(
        endpoint.url,
        data=payload_text.encode(),
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Playto-Signature': signature,
            'X-Playto-Event': event.event_type,
        },
    )

    success = False
    response_code = None
    response_body = ''
    try:
        with urlrequest.urlopen(req, timeout=5) as response:
            response_code = response.getcode()
            response_body = response.read().decode(errors='ignore')
            success = 200 <= response_code < 300
    except Exception as exc:
        response_body = str(exc)

    last_attempt = (
        WebhookDeliveryAttempt.objects.filter(event=event, endpoint=endpoint)
        .order_by('-attempt_number')
        .first()
    )
    attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1
    WebhookDeliveryAttempt.objects.create(
        event=event,
        endpoint=endpoint,
        response_code=response_code,
        response_body=response_body[:5000],
        success=success,
        attempt_number=attempt_number,
    )
    return success, response_body


def _enforce_payout_risk_limits(*, merchant_id: int, amount_paise: int) -> None:
    from .models import MerchantRiskProfile

    profile, _ = MerchantRiskProfile.objects.get_or_create(merchant_id=merchant_id)
    if amount_paise > profile.max_single_payout_paise:
        raise RiskRuleViolationError(
            f"Requested amount exceeds per-payout limit of {profile.max_single_payout_paise} paise"
        )

    now = timezone.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_qs = Payout.objects.filter(merchant_id=merchant_id, created_at__gte=start_of_day)
    daily_amount = today_qs.aggregate(total=Sum('amount_paise'))['total'] or 0
    daily_count = today_qs.count()

    if daily_amount + amount_paise > profile.daily_payout_limit_paise:
        raise RiskRuleViolationError(
            f"Daily payout amount limit exceeded ({profile.daily_payout_limit_paise} paise)"
        )
    if daily_count + 1 > profile.daily_payout_count_limit:
        raise RiskRuleViolationError(
            f"Daily payout count limit exceeded ({profile.daily_payout_count_limit})"
        )
