from django.contrib import admin

from .models import (
    ApiKey,
    BankAccount,
    EventOutbox,
    IdempotencyKey,
    LedgerEntry,
    Merchant,
    MerchantRiskProfile,
    MerchantUser,
    Payout,
    WebhookDeliveryAttempt,
    WebhookEndpoint,
)

admin.site.register(Merchant)
admin.site.register(MerchantUser)
admin.site.register(MerchantRiskProfile)
admin.site.register(BankAccount)
admin.site.register(LedgerEntry)
admin.site.register(Payout)
admin.site.register(IdempotencyKey)
admin.site.register(ApiKey)
admin.site.register(WebhookEndpoint)
admin.site.register(EventOutbox)
admin.site.register(WebhookDeliveryAttempt)
