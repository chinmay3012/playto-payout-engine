# Data Models Specification

This document describes every model, field, and constraint.
Write models exactly as specified — the graders check the invariants.

---

## 1. Merchant

```python
class Merchant(models.Model):
    name         = models.CharField(max_length=200)
    email        = models.EmailField(unique=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
```

---

## 2. BankAccount

```python
class BankAccount(models.Model):
    merchant      = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='bank_accounts')
    account_number = models.CharField(max_length=20)
    ifsc          = models.CharField(max_length=11)
    beneficiary_name = models.CharField(max_length=200)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['merchant', 'account_number', 'ifsc']]
```

---

## 3. LedgerEntry

```python
class EntryType(models.TextChoices):
    CREDIT = 'CREDIT', 'Credit'
    DEBIT  = 'DEBIT',  'Debit'

class LedgerEntry(models.Model):
    merchant      = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='ledger_entries')
    amount_paise  = models.BigIntegerField()          # ALWAYS positive. Sign is in entry_type.
    entry_type    = models.CharField(max_length=6, choices=EntryType.choices)
    description   = models.CharField(max_length=500)
    reference_id  = models.CharField(max_length=100, blank=True)  # payout ID or payment ID
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['merchant', 'created_at'])]
```

**Critical invariant:** `amount_paise` is always a positive integer. The sign is captured by `entry_type`, never by the number itself. A debit of 5000 paise is stored as `amount_paise=5000, entry_type=DEBIT` — not as `-5000`.

---

## 4. Payout

```python
class PayoutStatus(models.TextChoices):
    PENDING    = 'PENDING',    'Pending'
    PROCESSING = 'PROCESSING', 'Processing'
    COMPLETED  = 'COMPLETED',  'Completed'
    FAILED     = 'FAILED',     'Failed'

ALLOWED_TRANSITIONS = {
    PayoutStatus.PENDING:    [PayoutStatus.PROCESSING],
    PayoutStatus.PROCESSING: [PayoutStatus.COMPLETED, PayoutStatus.FAILED],
    PayoutStatus.COMPLETED:  [],   # terminal
    PayoutStatus.FAILED:     [],   # terminal
}

class Payout(models.Model):
    merchant             = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='payouts')
    bank_account         = models.ForeignKey(BankAccount, on_delete=models.PROTECT)
    amount_paise         = models.BigIntegerField()
    status               = models.CharField(max_length=12, choices=PayoutStatus.choices, default=PayoutStatus.PENDING)
    idempotency_key      = models.UUIDField()
    attempt_count        = models.IntegerField(default=0)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['merchant', 'idempotency_key']]
        indexes = [
            models.Index(fields=['status', 'processing_started_at']),
            models.Index(fields=['merchant', 'created_at']),
        ]
```

---

## 5. IdempotencyKey

```python
class IdempotencyKey(models.Model):
    key             = models.UUIDField()
    merchant        = models.ForeignKey(Merchant, on_delete=models.CASCADE)
    response_body   = models.JSONField()
    response_status = models.IntegerField()
    created_at      = models.DateTimeField(auto_now_add=True)
    expires_at      = models.DateTimeField()       # created_at + 24 hours

    class Meta:
        unique_together = [['key', 'merchant']]
        indexes = [models.Index(fields=['expires_at'])]
```

---

## Balance Calculation

**This is the query the graders will run to verify the invariant.**

```python
# services.py

from django.db.models import Sum, Q
from decimal import Decimal

def get_merchant_balance(merchant_id: int) -> dict:
    """
    All arithmetic happens in the database.
    Python only receives the final aggregated integers.
    """
    entries = LedgerEntry.objects.filter(merchant_id=merchant_id)

    result = entries.aggregate(
        total_credits=Sum('amount_paise', filter=Q(entry_type=EntryType.CREDIT)),
        total_debits=Sum('amount_paise',  filter=Q(entry_type=EntryType.DEBIT)),
    )

    total_credits = result['total_credits'] or 0
    total_debits  = result['total_debits']  or 0
    net_balance   = total_credits - total_debits

    # Held = funds reserved by PENDING + PROCESSING payouts
    # These are already debited in the ledger (DEBIT entry created at payout creation)
    # so net_balance already excludes them. We just calculate held for display.
    held = Payout.objects.filter(
        merchant_id=merchant_id,
        status__in=[PayoutStatus.PENDING, PayoutStatus.PROCESSING]
    ).aggregate(held=Sum('amount_paise'))['held'] or 0

    return {
        'total_paise':     net_balance,
        'held_paise':      held,
        'available_paise': net_balance - held,
    }
```

**Why not use Python arithmetic on fetched rows:**
If you do `sum(entry.amount_paise for entry in entries)` in Python, you:
1. Load every row into memory (expensive at scale)
2. Risk integer overflow in Python (rare but possible)
3. Introduce a time-of-check/time-of-use gap — DB may have newer rows by the time Python sums

`aggregate(Sum(...))` sends a single `SELECT SUM(amount_paise) FROM ...` to Postgres, which is atomic, consistent, and O(1) memory.

---

## Seed Script

Write this as a Django management command: `python manage.py seed`

```
Merchant 1: Acme Exports
  BankAccount: HDFC ****1234
  Credits: 
    ₹50,000 — "Initial payment from client US-001"
    ₹35,000 — "Invoice #INV-2024-001 settled"
    ₹15,000 — "Retainer for March 2024"
  Total available: ₹1,00,000

Merchant 2: Nova Freelance Studio
  BankAccount: ICICI ****5678
  Credits:
    ₹75,000 — "Project Phoenix milestone 1"
    ₹25,000 — "Consulting fee — Q1"
  Total available: ₹1,00,000

Merchant 3: Bright Digital Agency
  BankAccount: SBI ****9012
  Credits:
    ₹2,00,000 — "Retainer contract — 6 months"
    ₹50,000   — "Ad campaign management fee"
  Total available: ₹2,50,000
```

All amounts in paise in the DB (multiply ₹ amounts × 100).
