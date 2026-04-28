# Cursor Prompting Guide — Playto Payout Engine

Use these prompts in Cursor (or Antigravity) to generate each section.
Each prompt is scoped to one file/feature to keep output focused and reviewable.

---

## Phase 1 — Models

```
Create Django models for a payout engine in apps/payouts/models.py.

Models needed:
1. Merchant: id, name, email, created_at
2. BankAccount: merchant (FK), account_number, ifsc, beneficiary_name, is_active, created_at
3. LedgerEntry: merchant (FK), amount_paise (BigIntegerField — never Float), entry_type (CREDIT/DEBIT choices), description, reference_id, created_at. amount_paise is always positive; sign is in entry_type.
4. Payout: merchant (FK), bank_account (FK), amount_paise (BigIntegerField), status (PENDING/PROCESSING/COMPLETED/FAILED choices, default PENDING), idempotency_key (UUIDField), attempt_count (IntegerField default 0), processing_started_at (DateTimeField nullable), created_at, updated_at (auto_now)
5. IdempotencyKey: key (UUIDField), merchant (FK), response_body (JSONField nullable), response_status (IntegerField nullable), created_at, expires_at (DateTimeField)

Add unique_together on Payout: (merchant, idempotency_key)
Add unique_together on IdempotencyKey: (key, merchant)
Add indexes on Payout: (status, processing_started_at) and (merchant, created_at)
Add Meta.indexes on LedgerEntry: (merchant, created_at)
```

---

## Phase 1 — Seed Command

```
Create a Django management command at apps/payouts/management/commands/seed.py.

Seed 3 merchants with bank accounts and credit ledger entries:
- Merchant 1: "Acme Exports" — credits totalling ₹1,00,000 (10,000,000 paise)
- Merchant 2: "Nova Freelance Studio" — credits totalling ₹1,00,000 (10,000,000 paise)  
- Merchant 3: "Bright Digital Agency" — credits totalling ₹2,50,000 (25,000,000 paise)

Each merchant gets one BankAccount and 2-3 LedgerEntry credits.
Use get_or_create so the command is idempotent (safe to run multiple times).
Print a summary at the end showing merchant names and balances.
```

---

## Phase 2 — Services (most critical)

```
Create apps/payouts/services.py with these functions:

1. get_merchant_balance(merchant_id: int) -> dict
   Returns {total_paise, held_paise, available_paise}.
   Use DB-level aggregate(Sum(...)) with Q filters for CREDIT and DEBIT separately.
   Never fetch rows and sum in Python.
   held_paise = sum of amount_paise for PENDING and PROCESSING payouts.

2. create_payout_request(merchant_id, amount_paise, bank_account_id, idempotency_key) -> Payout
   Must use transaction.atomic() with select_for_update() on the Merchant row.
   Calculate balance INSIDE the locked transaction using aggregate().
   If insufficient, raise InsufficientBalanceError.
   Create a LedgerEntry(type=DEBIT) and Payout(status=PENDING) atomically.
   Do NOT enqueue Celery task inside this function.

3. transition_payout_status(payout_id: int, new_status: str) -> Payout
   Define ALLOWED_TRANSITIONS = {PENDING: [PROCESSING], PROCESSING: [COMPLETED, FAILED], COMPLETED: [], FAILED: []}
   Use select_for_update() inside atomic().
   Use filtered update Payout.objects.filter(id=payout_id, status=current_status).update(new_status).
   If updated_count == 0, raise InvalidTransitionError.
   Set processing_started_at when transitioning to PROCESSING.

4. fail_payout_and_return_funds(payout_id: int)
   Must be atomic: transition to FAILED + create LedgerEntry(type=CREDIT) in one transaction.

Create exceptions.py with: InsufficientBalanceError, InvalidTransitionError, KeyInFlightError.
```

---

## Phase 2 — Views

```
Create apps/payouts/views.py with DRF APIViews.

Endpoints:
1. GET /api/v1/merchants/ — list all merchants
2. GET /api/v1/merchants/{id}/balance/ — call get_merchant_balance()
3. GET /api/v1/merchants/{id}/ledger/ — paginated LedgerEntry queryset, newest first
4. POST /api/v1/payouts/ — payout creation with idempotency
5. GET /api/v1/payouts/{id}/ — payout detail
6. GET /api/v1/merchants/{id}/payouts/ — paginated payout list

For POST /api/v1/payouts/:
- Read Idempotency-Key header, validate it's a UUID, return 400 if missing/invalid
- Check IdempotencyKey table: if found and response_body not null, return stored response with status 200
- If found and response_body is null, return 409 KEY_IN_FLIGHT
- Use get_or_create to reserve the key atomically
- Call create_payout_request() service
- Store response in IdempotencyKey table
- Enqueue process_payout_task.delay(payout.id)
- Return 201

Handle InsufficientBalanceError → 402, InvalidTransitionError → 422.
Return consistent error JSON: {"error": "ERROR_CODE", "detail": "..."}
```

---

## Phase 3 — Celery Tasks

```
Create apps/payouts/tasks.py with Celery tasks.

1. process_payout_task(payout_id: int) — @shared_task(bind=True, max_retries=3)
   - Call transition_payout_status(payout_id, 'PROCESSING')
   - Simulate bank with random.random():
     - <0.70: sleep 1-3s, call transition_payout_status(payout_id, 'COMPLETED')
     - <0.90: sleep 0.5-2s, call fail_payout_and_return_funds(payout_id)
     - else: sleep 40s (simulates hang — stuck detection picks this up)
   - Handle InvalidTransitionError silently (payout already in terminal state)

2. retry_stuck_payouts() — @shared_task, scheduled via Celery beat every 30s
   - Find Payout.objects.filter(status='PROCESSING', processing_started_at__lt=now-30s)
   - For each: if attempt_count >= 3, call fail_payout_and_return_funds()
   - Otherwise: reset to PENDING, increment attempt_count, re-enqueue with exponential backoff (30 * 2^attempt_count seconds)

Add to config/celery.py:
- CELERY_BEAT_SCHEDULE with retry-stuck-payouts every 30 seconds
```

---

## Phase 4 — React Components

```
Create React components for the Playto payout dashboard.

BalanceCard.jsx:
- Props: merchantId
- Fetch GET /api/v1/merchants/{id}/balance/ on mount and every 5s
- Display available (green), held (amber), total (gray) in ₹ (paise / 100, 2 decimal places)

PayoutForm.jsx:
- Props: merchantId, bankAccounts, onSuccess
- Amount input in ₹ (user types rupees, convert to paise before sending)
- Bank account dropdown
- On submit: generate fresh UUID with crypto.randomUUID(), POST /api/v1/payouts/ with Idempotency-Key header
- Show error messages from API (insufficient balance, etc.)
- Clear and call onSuccess() on 201

PayoutHistory.jsx:
- Props: merchantId
- Fetch GET /api/v1/merchants/{id}/payouts/ on mount and every 5s
- Table: ID, amount (₹), status badge, created_at
- Status badge colours: PENDING=gray, PROCESSING=amber, COMPLETED=green, FAILED=red

LedgerTable.jsx:
- Props: merchantId
- Fetch GET /api/v1/merchants/{id}/ledger/
- Table: type (credit/debit icon), amount (₹), description, date
- Credits in green, debits in red

Use Tailwind for styling. Use axios for API calls with base URL from import.meta.env.VITE_API_BASE_URL.
```

---

## Phase 5 — Tests

```
Create Django tests in apps/payouts/tests/.

test_concurrency.py:
- Use TransactionTestCase (not TestCase — SELECT FOR UPDATE requires actual commits)
- Set up merchant with ₹100 balance (10000 paise)
- Use threading.Thread to fire two simultaneous POST /api/v1/payouts/ requests for ₹60 each
- Assert exactly one 201 and one 402
- Assert total debits in ledger = 6000 paise (not 12000)
- Assert balance never went negative

test_idempotency.py:
- Use TestCase
- POST with key K1 → assert 201
- POST again with key K1 → assert 200, same payout ID in response
- Assert only one Payout row exists for key K1
- Assert only one LedgerEntry debit exists
- POST with key K2 → assert 201, different payout ID
- POST with key K1 for a different merchant → assert 201, treated as new request
```
