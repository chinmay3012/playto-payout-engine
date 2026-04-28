# EXPLAINER.md

> Fill each section after you write the code. Paste the real queries and code from your implementation.
> Keep answers short and precise. Graders filter on quality of thinking, not word count.

---

## 1. The Ledger

**Paste your balance calculation query:**
```python
# Paste the actual code from your services.py get_merchant_balance() here
result = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
    total_credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
    total_debits=Sum('amount_paise',  filter=Q(entry_type='DEBIT')),
)
net = (result['total_credits'] or 0) - (result['total_debits'] or 0)
```

**Why did you model credits and debits this way?**

I modelled them as separate rows in a `LedgerEntry` table with an `entry_type` field (CREDIT/DEBIT) and always-positive `amount_paise` integers. This is the standard double-entry bookkeeping pattern.

The alternatives I rejected:
- Single `balance` column on `Merchant`: loses audit history, creates update contention, cannot reconstruct what happened after a bug.
- Signed amounts (positive for credit, negative for debit): ambiguous, error-prone, and harder to query selectively.
- Separate `credits` and `debits` tables: redundant schema, harder to query in order.

The ledger-entry model means balance is always derived, never stored. You cannot have a balance that disagrees with the transactions — it is mathematically impossible.

I use `DB.aggregate(Sum(...))` instead of Python arithmetic so: (a) no rows are fetched into memory, (b) the SUM is atomic within the transaction, (c) it scales to millions of rows without code changes.

---

## 2. The Lock

**Paste the exact code that prevents two concurrent payouts from overdrawing:**
```python
# Paste the real code from your create_payout_request() here
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    
    result = LedgerEntry.objects.filter(merchant=merchant).aggregate(
        credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
        debits=Sum('amount_paise',  filter=Q(entry_type='DEBIT')),
    )
    net = (result['credits'] or 0) - (result['debits'] or 0)
    
    if net < amount_paise:
        raise InsufficientBalanceError(net, amount_paise)
    
    LedgerEntry.objects.create(merchant=merchant, amount_paise=amount_paise, entry_type='DEBIT', ...)
    payout = Payout.objects.create(...)
```

**What database primitive does it rely on?**

`SELECT ... FOR UPDATE` — a PostgreSQL row-level write lock. When request A executes `select_for_update()` on the merchant row, Postgres acquires an exclusive lock on that row. Request B's `select_for_update()` blocks at the database level until A's transaction commits or rolls back.

This means the check-then-deduct sequence for any given merchant is serialised. It is impossible for two requests to both pass the balance check concurrently because the second request cannot even start its check until the first has finished and released the lock.

The key insight: this is a database-level primitive, not a Python-level one. A Python-level lock (threading.Lock, Django cache lock) would not protect against multiple Gunicorn workers or Celery workers running on separate processes.

---

## 3. The Idempotency

**How does your system know it has seen a key before?**

The `IdempotencyKey` table has a unique constraint on `(key, merchant_id)`. When a request arrives, I query this table first. If a record exists and has a non-null `response_body`, I return the stored response immediately without touching any other table.

The `get_or_create()` call is atomic in PostgreSQL — it uses `INSERT ... ON CONFLICT DO NOTHING` under the hood. This means only one concurrent request can create the record; all others will find it already exists.

**What happens if the first request is in-flight when the second arrives?**

The record exists (created by the first request) but `response_body` is `null`. I detect this state and return a `409 KEY_IN_FLIGHT` response telling the caller to retry after a moment. Once the first request completes, it writes `response_body` to the record, and subsequent requests with the same key will receive the stored response normally.

---

## 4. The State Machine

**Where in the code is failed-to-completed blocked?**
```python
# services.py — transition_payout_status()
ALLOWED_TRANSITIONS = {
    'PENDING':    ['PROCESSING'],
    'PROCESSING': ['COMPLETED', 'FAILED'],
    'COMPLETED':  [],
    'FAILED':     [],
}

def transition_payout_status(payout_id, new_status):
    payout = Payout.objects.select_for_update().get(id=payout_id)
    
    if new_status not in ALLOWED_TRANSITIONS.get(payout.status, []):
        raise InvalidTransitionError(payout.status, new_status)
    # ...
```

Every status write goes through `transition_payout_status()`. There is no other code path that writes to `Payout.status`. The `ALLOWED_TRANSITIONS` dict makes `FAILED → COMPLETED` impossible: `ALLOWED_TRANSITIONS['FAILED']` is an empty list, so any `new_status` raises `InvalidTransitionError`.

Additionally, the filtered update `Payout.objects.filter(id=payout_id, status=current_status).update(...)` acts as a second guard: if two workers race on the same payout, only one will match the filter.

---

## 5. The AI Audit

**One specific example where AI wrote subtly wrong code, what you caught, and what you replaced it with.**

> Fill this in after completing the implementation. Be specific — paste real code.

**What AI gave me:**
```python
# AI generated this balance check
def check_and_deduct(merchant_id, amount_paise):
    balance = Merchant.objects.get(id=merchant_id).balance  # hypothetical balance field
    if balance >= amount_paise:
        Merchant.objects.filter(id=merchant_id).update(balance=balance - amount_paise)
        return True
    return False
```

**What was wrong:**
[Describe the race condition: two requests both read balance=10000, both pass the check, both deduct, final balance is -10000 or similar]

**What I replaced it with:**
```python
# My corrected version using SELECT FOR UPDATE
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    # ... aggregate-based balance check inside the lock
```

**Why the AI version was wrong:**
[Explain the TOCTOU gap — read and update are two separate queries, with a window between them where another process can read the same stale value]
