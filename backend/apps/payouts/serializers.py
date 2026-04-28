from rest_framework import serializers

from .models import (
    ApiKey,
    BankAccount,
    LedgerEntry,
    Merchant,
    MerchantRiskProfile,
    MerchantUser,
    Payout,
    WebhookEndpoint,
    WebhookDeliveryAttempt,
)


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ['id', 'name', 'email']


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = [
            'id',
            'entry_type',
            'amount_paise',
            'description',
            'reference_id',
            'created_at',
        ]


class BankAccountMaskedSerializer(serializers.ModelSerializer):
    account_number = serializers.SerializerMethodField()

    class Meta:
        model = BankAccount
        fields = ['id', 'account_number', 'ifsc']

    def get_account_number(self, obj):
        if len(obj.account_number) <= 4:
            return obj.account_number
        return f"****{obj.account_number[-4:]}"


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ['id', 'account_number', 'ifsc', 'beneficiary_name', 'is_active']


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = [
            'id',
            'merchant_id',
            'amount_paise',
            'bank_account_id',
            'status',
            'idempotency_key',
            'attempt_count',
            'created_at',
            'updated_at',
        ]


class PayoutDetailSerializer(serializers.ModelSerializer):
    bank_account = BankAccountMaskedSerializer(read_only=True)

    class Meta:
        model = Payout
        fields = [
            'id',
            'merchant_id',
            'amount_paise',
            'bank_account',
            'status',
            'attempt_count',
            'idempotency_key',
            'created_at',
            'updated_at',
        ]


class PayoutRequestSerializer(serializers.Serializer):
    merchant_id = serializers.IntegerField()
    amount_paise = serializers.IntegerField(min_value=1)
    bank_account_id = serializers.IntegerField()


class BalanceSerializer(serializers.Serializer):
    merchant_id = serializers.IntegerField()
    available_paise = serializers.IntegerField()
    held_paise = serializers.IntegerField()
    total_paise = serializers.IntegerField()
    available_inr = serializers.CharField()
    held_inr = serializers.CharField()
    total_inr = serializers.CharField()


class ApiKeyCreateSerializer(serializers.Serializer):
    merchant_id = serializers.IntegerField()
    name = serializers.CharField(max_length=100)
    scopes = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
    )
    expires_in_days = serializers.IntegerField(min_value=1, max_value=3650, required=False)


class ApiKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiKey
        fields = [
            'id',
            'merchant_id',
            'name',
            'key_prefix',
            'scopes',
            'is_active',
            'last_used_at',
            'expires_at',
            'created_at',
        ]


class WebhookEndpointCreateSerializer(serializers.Serializer):
    merchant_id = serializers.IntegerField()
    url = serializers.URLField(max_length=500)


class WebhookEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = ['id', 'merchant_id', 'url', 'is_active', 'created_at']


class MerchantUserRegisterSerializer(serializers.Serializer):
    merchant_id = serializers.IntegerField()
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8)
    role = serializers.ChoiceField(
        choices=MerchantUser.Role.choices, default=MerchantUser.Role.OPERATOR
    )


class MerchantUserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class MerchantRiskProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantRiskProfile
        fields = [
            'merchant_id',
            'max_single_payout_paise',
            'daily_payout_limit_paise',
            'daily_payout_count_limit',
            'updated_at',
        ]


class WebhookDeliveryAttemptSerializer(serializers.ModelSerializer):
    event_type = serializers.CharField(source='event.event_type', read_only=True)
    endpoint_url = serializers.CharField(source='endpoint.url', read_only=True)

    class Meta:
        model = WebhookDeliveryAttempt
        fields = [
            'id',
            'event_id',
            'event_type',
            'endpoint_id',
            'endpoint_url',
            'response_code',
            'response_body',
            'success',
            'attempt_number',
            'created_at',
        ]
