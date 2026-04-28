# Critical Implementation Notes

These are the exact patterns to implement. The graders check these specifically.
Do not deviate without understanding why.

---

## 1. Concurrency — The Lock

This is the most common failure point. Do NOT check balance in Python then deduct in a separate query.

**Wrong pattern (race condition):**
```python
# BAD — time-of-check/time-of-use gap
balance = get_merchant_balance(merchant_id)        # read 1
if balance['available_paise'] >= amount_paise:
    # another request can slip in here and pass the same check
    create_debit_entry(merchant_id, amount_paise)  # write 1
```

**Correct pattern:**
```python
# services.py

from django.db import transaction
from django.db.models import Sum, Q
from django.db.models import F

def create_payout_request(merchant_id, amount_paise, bank_account_id, idempotency_key):
    with transaction.atomic():
        # Lock the merchant row — serialises concurrent requests for this merchant
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)
        
        # Calculate balance INSIDE the transaction, AFTER acquiring the lock
        result = LedgerEntry.objects.filter(merchant=merchant).aggregate(
            credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
            debits=Sum('amount_paise',  filter=Q(entry_type='DEBIT')),
        )
        net = (result['credits'] or 0) - (result['debits'] or 0)
        
        if net < amount_paise:
            raise InsufficientBalanceError(available=net, requested=amount_paise)
        
        # Debit and create payout atomically
        LedgerEntry.objects.create(
            merchant=merchant,
            amount_paise=amount_paise,
            entry_type='DEBIT',
            description=f'Payout initiated',
        )
        payout = Payout.objects.create(
            merchant=merchant,
            bank_account_id=bank_account_id,
            amount_paise=amount_paise,
            status='PENDING',
            idempotency_key=idempotency_key,
        )
    
    # Enqueue AFTER the transaction commits
    process_payout_task.delay(payout.id)
    return payout
```

**The primitive:** `SELECT ... FOR UPDATE` — a PostgreSQL row-level lock. When request A holds this lock, request B's `select_for_update()` call blocks at the DB level until A's transaction commits or rolls back. The two requests are serialised — one completes, then the other starts. No race condition possible.

---

## 2. Idempotency — The Lookup

**The flow:**
```
Incoming request with key K
        │
        ▼
Does IdempotencyKey(key=K, merchant=M) exist?
        │
   YES  │  NO
        │   └──► Is key in-flight? (created, no response yet)
        │              │
        │         YES  │  NO
        │              │   └──► Process request normally
        │              │        Store response in IdempotencyKey
        │              │        Return 201
        │              │
        │         Return 409
        │
        ▼
Return stored response (200)
```

**Implementation:**
```python
def handle_payout_request(merchant_id, amount_paise, bank_account_id, idempotency_key):
    from django.utils import timezone
    
    now = timezone.now()
    
    # Check for existing key (not expired)
    try:
        existing = IdempotencyKey.objects.get(
            key=idempotency_key,
            merchant_id=merchant_id,
            expires_at__gt=now,
        )
        # Key seen before — return stored response
        return existing.response_body, existing.response_status
    except IdempotencyKey.DoesNotExist:
        pass
    
    # Reserve the key atomically to handle in-flight scenario
    # get_or_create is atomic in PostgreSQL (uses INSERT ... ON CONFLICT)
    key_record, created = IdempotencyKey.objects.get_or_create(
        key=idempotency_key,
        merchant_id=merchant_id,
        defaults={
            'response_body': None,    # no response yet
            'response_status': None,
            'expires_at': now + timedelta(hours=24),
        }
    )
    
    if not created and key_record.response_body is None:
        # Key was created by another in-flight request but not yet completed
        raise KeyInFlightError()
    
    if not created and key_record.response_body is not None:
        # Another concurrent request already completed — return its response
        return key_record.response_body, key_record.response_status
    
    # New key — process request
    try:
        payout = create_payout_request(merchant_id, amount_paise, bank_account_id, idempotency_key)
        response_body = PayoutSerializer(payout).data
        response_status = 201
    except InsufficientBalanceError as e:
        response_body = {'error': 'INSUFFICIENT_BALANCE', 'detail': str(e)}
        response_status = 402
    
    # Store response so replay returns the same thing
    key_record.response_body = response_body
    key_record.response_status = response_status
    key_record.save(update_fields=['response_body', 'response_status'])
    
    return response_body, response_status
```

---

## 3. State Machine — Transition Enforcement

```python
# exceptions.py
class InvalidTransitionError(Exception):
    def __init__(self, from_status, to_status):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid transition: {from_status} → {to_status}")

# services.py
ALLOWED_TRANSITIONS = {
    'PENDING':    ['PROCESSING'],
    'PROCESSING': ['COMPLETED', 'FAILED'],
    'COMPLETED':  [],
    'FAILED':     [],
}

def transition_payout_status(payout_id: int, new_status: str) -> Payout:
    """
    Atomically transitions a payout to a new status.
    Uses a filtered update to prevent TOCTOU races.
    Raises InvalidTransitionError if the transition is not allowed.
    """
    payout = Payout.objects.select_for_update().get(id=payout_id)
    
    if new_status not in ALLOWED_TRANSITIONS.get(payout.status, []):
        raise InvalidTransitionError(payout.status, new_status)
    
    # Use filtered update — if status changed between our read and write, 
    # updated_count will be 0 and we know a race occurred
    extra_fields = {}
    if new_status == 'PROCESSING':
        extra_fields['processing_started_at'] = timezone.now()
    
    updated_count = Payout.objects.filter(
        id=payout_id,
        status=payout.status,   # guard: only update if current status matches
    ).update(status=new_status, **extra_fields)
    
    if updated_count == 0:
        raise InvalidTransitionError(payout.status, new_status)  # raced
    
    payout.refresh_from_db()
    return payout
```

**On failure — return funds atomically:**
```python
def fail_payout_and_return_funds(payout_id: int):
    with transaction.atomic():
        payout = transition_payout_status(payout_id, 'FAILED')
        
        # Credit MUST happen in the same transaction as the status update
        LedgerEntry.objects.create(
            merchant=payout.merchant,
            amount_paise=payout.amount_paise,
            entry_type='CREDIT',
            description=f'Payout #{payout.id} failed — funds returned',
            reference_id=str(payout.id),
        )
```

---

## 4. Celery Worker — Bank Simulator

```python
# tasks.py
import random
import time
from celery import shared_task

@shared_task(bind=True, max_retries=3)
def process_payout_task(self, payout_id: int):
    from .services import transition_payout_status, fail_payout_and_return_funds
    
    try:
        payout = transition_payout_status(payout_id, 'PROCESSING')
    except InvalidTransitionError:
        # Already processing or terminal — do not retry
        return
    
    # Simulate bank settlement
    outcome = random.random()
    
    if outcome < 0.70:
        # Success
        time.sleep(random.uniform(1, 3))
        transition_payout_status(payout_id, 'COMPLETED')
    
    elif outcome < 0.90:
        # Failure
        time.sleep(random.uniform(0.5, 2))
        fail_payout_and_return_funds(payout_id)
    
    else:
        # Hang — sleep longer than the stuck-detection threshold
        time.sleep(40)
        # Worker will be detected as stuck by the beat task and retried
```

**Stuck payout retry (Celery beat task):**
```python
@shared_task
def retry_stuck_payouts():
    """
    Runs every 30 seconds via Celery beat.
    Finds payouts stuck in PROCESSING for >30s and retries or fails them.
    """
    cutoff = timezone.now() - timedelta(seconds=30)
    
    stuck = Payout.objects.filter(
        status='PROCESSING',
        processing_started_at__lt=cutoff,
    )
    
    for payout in stuck:
        if payout.attempt_count >= 3:
            fail_payout_and_return_funds(payout.id)
        else:
            Payout.objects.filter(id=payout.id).update(
                status='PENDING',
                attempt_count=F('attempt_count') + 1,
                processing_started_at=None,
            )
            delay = 30 * (2 ** payout.attempt_count)  # exponential backoff
            process_payout_task.apply_async(args=[payout.id], countdown=delay)
```

**Celery beat config in settings:**
```python
CELERY_BEAT_SCHEDULE = {
    'retry-stuck-payouts': {
        'task': 'apps.payouts.tasks.retry_stuck_payouts',
        'schedule': 30.0,  # every 30 seconds
    },
}
```

---

## 5. Paise / INR conversion

Convert paise → INR only at the display boundary (serializers or frontend).
Never convert for business logic.

```python
# serializers.py — display helper
def paise_to_inr_str(paise: int) -> str:
    """Converts integer paise to INR string with 2 decimal places."""
    return f"{paise / 100:.2f}"
```

In React:
```js
// utils.js
export const paiseToINR = (paise) => (paise / 100).toFixed(2)
export const INRtoPaise = (inr) => Math.round(parseFloat(inr) * 100)
```

---

## 6. Idempotency key — frontend usage

Each time the user submits a new payout from the form, generate a fresh UUID:
```js
import { v4 as uuidv4 } from 'uuid'

const handleSubmit = async () => {
  const idempotencyKey = uuidv4()  // new key per submission attempt
  
  await axios.post('/api/v1/payouts/', payload, {
    headers: { 'Idempotency-Key': idempotencyKey }
  })
}
```

On network timeout, the user may retry. To replay (idempotent retry), pass the same key:
```js
const handleRetry = async () => {
  // reuse the SAME key as the failed attempt
  await axios.post('/api/v1/payouts/', payload, {
    headers: { 'Idempotency-Key': lastUsedKey }
  })
}
```
