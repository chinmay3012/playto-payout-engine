from django.db import models
from django.utils import timezone
import secrets
from django.contrib.auth.models import User


class Merchant(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class MerchantUser(models.Model):
    class Role(models.TextChoices):
        USER = 'USER', 'User'
        OWNER = 'OWNER', 'Owner'
        ADMIN = 'ADMIN', 'Admin'
        OPERATOR = 'OPERATOR', 'Operator'
        VIEWER = 'VIEWER', 'Viewer'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='merchant_profile')
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='users')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OPERATOR)
    is_active = models.BooleanField(default=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MerchantRiskProfile(models.Model):
    merchant = models.OneToOneField(
        Merchant, on_delete=models.CASCADE, related_name='risk_profile'
    )
    max_single_payout_paise = models.BigIntegerField(default=1_000_000_00)  # 10 lakh
    daily_payout_limit_paise = models.BigIntegerField(default=5_000_000_00)  # 50 lakh
    daily_payout_count_limit = models.IntegerField(default=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BankAccount(models.Model):
    merchant = models.ForeignKey(
        Merchant, on_delete=models.CASCADE, related_name='bank_accounts'
    )
    account_number = models.CharField(max_length=20)
    ifsc = models.CharField(max_length=11)
    beneficiary_name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['merchant', 'account_number', 'ifsc']]


class EntryType(models.TextChoices):
    CREDIT = 'CREDIT', 'Credit'
    DEBIT = 'DEBIT', 'Debit'


class LedgerEntry(models.Model):
    merchant = models.ForeignKey(
        Merchant, on_delete=models.PROTECT, related_name='ledger_entries'
    )
    amount_paise = models.BigIntegerField()
    entry_type = models.CharField(max_length=6, choices=EntryType.choices)
    description = models.CharField(max_length=500)
    reference_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['merchant', 'created_at'])]


class PayoutStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PROCESSING = 'PROCESSING', 'Processing'
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed'


class Payout(models.Model):
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='payouts')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()
    status = models.CharField(
        max_length=12, choices=PayoutStatus.choices, default=PayoutStatus.PENDING
    )
    idempotency_key = models.UUIDField()
    attempt_count = models.IntegerField(default=0)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['merchant', 'idempotency_key']]
        indexes = [
            models.Index(fields=['status', 'processing_started_at']),
            models.Index(fields=['merchant', 'created_at']),
        ]


class IdempotencyKey(models.Model):
    key = models.UUIDField()
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE)
    response_body = models.JSONField(null=True, blank=True)
    response_status = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        unique_together = [['key', 'merchant']]
        indexes = [models.Index(fields=['expires_at'])]


class ApiKey(models.Model):
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=100)
    key_prefix = models.CharField(max_length=12, db_index=True)
    hashed_key = models.CharField(max_length=128, unique=True)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def generate_raw_key() -> str:
        return f'pk_live_{secrets.token_urlsafe(32)}'

    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())


class WebhookEndpoint(models.Model):
    merchant = models.ForeignKey(
        Merchant, on_delete=models.CASCADE, related_name='webhook_endpoints'
    )
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class EventOutbox(models.Model):
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='outbox_events')
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending'),
            ('PROCESSING', 'Processing'),
            ('DISPATCHED', 'Dispatched'),
            ('FAILED', 'Failed'),
        ],
        default='PENDING',
    )
    retry_count = models.IntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'created_at'])]


class WebhookDeliveryAttempt(models.Model):
    event = models.ForeignKey(
        EventOutbox, on_delete=models.CASCADE, related_name='delivery_attempts'
    )
    endpoint = models.ForeignKey(
        WebhookEndpoint, on_delete=models.CASCADE, related_name='delivery_attempts'
    )
    response_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    success = models.BooleanField(default=False)
    attempt_number = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
