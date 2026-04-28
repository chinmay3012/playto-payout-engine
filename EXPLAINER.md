# EXPLAINER.md

## 1. The Ledger

**Paste your balance calculation query:**
```python
# apps/payouts/services.py
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
```

**Why did you model credits and debits this way?**

I store every money movement as an append-only `LedgerEntry` row with positive `amount_paise` and explicit `entry_type` (`CREDIT`/`DEBIT`). This keeps a full audit trail and avoids mutable balance fields that drift under concurrency bugs.

Balance is always derived with DB aggregates, so there is no Python-side row iteration for financial checks.

## 2. The Lock

**Paste the exact code that prevents two concurrent payouts from overdrawing:**
```python
# apps/payouts/services.py
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    bank_account = BankAccount.objects.get(
        id=bank_account_id, merchant_id=merchant_id, is_active=True
    )

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
```

**What database primitive does it rely on?**

`SELECT ... FOR UPDATE` on the `Merchant` row inside a single `transaction.atomic()` block. This serializes payout creation per merchant so two concurrent requests cannot both pass the same balance check.

## 3. The Idempotency

**How does your system know it has seen a key before?**

`IdempotencyKey` has a unique constraint on `(key, merchant)`. In the payout endpoint I first query non-expired keys for that merchant.

- if `response_body` exists: return stored response (`200` replay)
- if row exists but `response_body` is null: return `409 KEY_IN_FLIGHT`
- else reserve with `get_or_create` and process

**What happens if the first request is in flight when the second arrives?**

The second request sees the same `(merchant, key)` row with null response and immediately receives:

```json
{
  "error": "KEY_IN_FLIGHT",
  "detail": "A request with this Idempotency-Key is currently being processed. Retry after a moment."
}
```

When the first finishes, the response body/status are stored on that key; later retries return the stored response.

## 4. The State Machine

**Where in the code is failed-to-completed blocked?**
```python
# apps/payouts/services.py
ALLOWED_TRANSITIONS = {
    PayoutStatus.PENDING: [PayoutStatus.PROCESSING],
    PayoutStatus.PROCESSING: [PayoutStatus.COMPLETED, PayoutStatus.FAILED],
    PayoutStatus.COMPLETED: [],
    PayoutStatus.FAILED: [],
}

if new_status not in ALLOWED_TRANSITIONS.get(current_status, []):
    raise InvalidTransitionError(current_status, new_status)
```

All status writes go through `transition_payout_status()`, so `FAILED -> COMPLETED` is rejected by design.

## 5. The AI Audit

**One specific example where AI wrote subtly wrong code, what you caught, and what you replaced it with.**

**What AI gave me (wrong pattern):**
```python
# read/check before locking
balance = get_merchant_balance(merchant_id)
if balance['available_paise'] < amount_paise:
    raise InsufficientBalanceError(...)

with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    # create payout + debit
```

**What was wrong:**

This introduces a TOCTOU race: two concurrent requests can both read the same pre-lock balance and then both proceed, overdrawing.

**What I replaced it with:**

I moved balance check inside the locked transaction (`select_for_update()` first, then aggregate/balance check, then debit+payout creation atomically).

**Why the AI version was wrong:**

The check and write were separated by a concurrency window. In money-moving code, check and mutation must happen under the same DB lock/transaction scope.

## 6. Two-Minute Demo Plan (for reviewer)

This is the fastest way to verify the graded parts live:

1. Start backend and worker:
```bash
python3 backend/manage.py migrate
python3 backend/manage.py seed
python3 backend/manage.py runserver 0.0.0.0:8000
python3 -m celery -A config.celery:app worker --loglevel=info --pool=solo
python3 -m celery -A config.celery:app beat --loglevel=info
```

2. Start frontend:
```bash
cd frontend
npm install
npm run dev
```

3. In UI:
- pick seeded merchant (`Acme Exports`)
- request payout from available bank account
- watch status polling in table every 5s (`PENDING -> PROCESSING -> COMPLETED/FAILED`)
- if FAILED, verify compensating credit appears in ledger

4. Deterministic API proof snippets:
```bash
# balance
curl http://localhost:8000/api/v1/merchants/1/balance/

# payouts list (shows status changes)
curl http://localhost:8000/api/v1/merchants/1/payouts/
```

This flow demonstrates ledger integrity, async lifecycle, and live status updates with minimal reviewer effort.
