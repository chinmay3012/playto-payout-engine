# Playto Payout Engine — Build Workflow

## Accounts and Auth (implemented)

- Multi-role accounts are available through `USER`, `OPERATOR`, `ADMIN`, and `OWNER` roles.
- Session auth now uses JWT cookies (`HttpOnly`) via:
  - `POST /api/v1/auth/register/`
  - `POST /api/v1/auth/login/`
  - `POST /api/v1/auth/refresh/`
  - `POST /api/v1/auth/logout/`
  - `GET /api/v1/auth/me/`
- Account management endpoints:
  - `PATCH /api/v1/account/profile/`
  - `POST /api/v1/account/change-password/`
- Role-protected sections:
  - `GET /api/v1/operator/home/` (operator/admin/owner)
  - `GET /api/v1/admin/home/` (admin/owner)
- Required backend env keys for cookie auth hardening:
  - `JWT_ACCESS_TOKEN_MINUTES`
  - `JWT_REFRESH_TOKEN_MINUTES`
  - `JWT_ACCESS_COOKIE_NAME`
  - `JWT_REFRESH_COOKIE_NAME`
  - `JWT_COOKIE_SECURE`
  - `JWT_COOKIE_SAMESITE`
  - `CORS_ALLOWED_ORIGINS`
  - `CSRF_TRUSTED_ORIGINS`

## Estimated effort: 
Organised in order of dependency. Do not skip Phase 1 — every later phase builds on the data model.

---

## Phase 0 — Repo & Environment Setup (30 min)

- [ ] Create GitHub repo: `playto-payout-engine`
- [ ] Initialise with `.gitignore` (Python, Node, .env)
- [ ] Set up project structure (see PROJECT_STRUCTURE.md)
- [ ] Create `.env.example` with all required variables
- [ ] First commit: `chore: initial project scaffold`

---

## Phase 1 — Data Model (2–3 hours) ⬅ Most critical

This is the foundation. Get it right before writing any API code.

### 1a. Merchant & Ledger model
- [ ] `Merchant` model: id, name, created_at
- [ ] `LedgerEntry` model: merchant (FK), amount_paise (BigIntegerField), entry_type (CREDIT/DEBIT), reference_id, created_at
- [ ] **No FloatField or DecimalField on amounts — BigIntegerField only**
- [ ] Balance = `SUM(credits) - SUM(debits)` via DB aggregation, never Python arithmetic on fetched rows

### 1b. BankAccount model
- [ ] `BankAccount` model: merchant (FK), account_number, ifsc, is_active
- [ ] One merchant can have multiple accounts

### 1c. Payout model
- [ ] `Payout` model: merchant (FK), bank_account (FK), amount_paise (BigIntegerField), status (PENDING/PROCESSING/COMPLETED/FAILED), idempotency_key, attempt_count, created_at, updated_at, processing_started_at
- [ ] `IdempotencyKey` model: key (UUID), merchant (FK), response_body (JSONField), response_status (int), created_at, expires_at

### 1d. Migrations & seed script
- [ ] Run migrations
- [ ] Write `seed.py` management command: 2–3 merchants, bank accounts, credit history
- [ ] Test that balance sum matches seeded credits

**Commit:** `feat: core data models — Merchant, LedgerEntry, Payout, IdempotencyKey`

---

## Phase 2 — API Layer (3–4 hours)

### 2a. Balance endpoint
- [ ] `GET /api/v1/merchants/{id}/balance/`
- [ ] Returns: available_paise, held_paise, total_paise
- [ ] available = total credits − total debits − held (pending/processing payouts)
- [ ] Use DB-level `aggregate(Sum(...))` — no Python loops

### 2b. Ledger endpoint
- [ ] `GET /api/v1/merchants/{id}/ledger/`
- [ ] Paginated list of LedgerEntry, newest first
- [ ] Include payout references where applicable

### 2c. Payout request endpoint — the hard part
- [ ] `POST /api/v1/payouts/`
- [ ] Reads `Idempotency-Key` header — validate it's a UUID
- [ ] Check IdempotencyKey table first — if found and not expired, return stored response
- [ ] If in-flight (created but no response yet): return 409 or wait (choose and document)
- [ ] **Concurrency: use `SELECT FOR UPDATE` on merchant ledger row, inside a transaction**
- [ ] Check available balance ≥ requested amount_paise **inside the transaction**
- [ ] Debit (hold) funds: create LedgerEntry(type=DEBIT) + Payout(status=PENDING)
- [ ] Store response in IdempotencyKey table
- [ ] Enqueue Celery task
- [ ] Return 201 with payout object

### 2d. Payout detail & list endpoints
- [ ] `GET /api/v1/payouts/{id}/`
- [ ] `GET /api/v1/merchants/{id}/payouts/`

**Commit:** `feat: payout request API with idempotency and concurrency lock`

---

## Phase 3 — Background Worker (2–3 hours)

### 3a. Payout processor task
- [ ] Celery task: `process_payout(payout_id)`
- [ ] Transition: PENDING → PROCESSING (atomic, reject if already PROCESSING/COMPLETED/FAILED)
- [ ] Set `processing_started_at = now()`
- [ ] Call bank simulator:
  - 70% → sleep 1–3s, return success
  - 20% → return failure
  - 10% → sleep 35s+ (simulates hang)
- [ ] On success: PROCESSING → COMPLETED, no ledger change (debit already recorded)
- [ ] On failure: PROCESSING → FAILED, **atomically** create CREDIT ledger entry to return funds

### 3b. State machine enforcement
- [ ] Write `transition_payout_status(payout, new_status)` utility
- [ ] Define allowed transitions dict: `{PENDING: [PROCESSING], PROCESSING: [COMPLETED, FAILED]}`
- [ ] Raise `InvalidTransitionError` for illegal moves
- [ ] Use DB-level update with `filter(status=expected_current)` to prevent races

### 3c. Retry logic
- [ ] Periodic Celery beat task: every 30s, find payouts stuck in PROCESSING for >30s
- [ ] Re-attempt with exponential backoff: attempt 1=30s, 2=60s, 3=120s
- [ ] After 3 attempts: transition to FAILED, return funds atomically

**Commit:** `feat: Celery worker — payout processor, state machine, retry logic`

---

## Phase 4 — React Frontend (2–3 hours)

### 4a. Project setup
- [ ] Vite + React + Tailwind
- [ ] Axios for API calls
- [ ] Set up API base URL from env

### 4b. Dashboard page
- [ ] Merchant selector (or hardcode merchant ID for demo)
- [ ] Balance card: available / held / total in ₹ (convert from paise: divide by 100)
- [ ] Recent credits/debits ledger table

### 4c. Payout form
- [ ] Amount input (in ₹, convert to paise before sending)
- [ ] Bank account selector (fetched from API)
- [ ] Auto-generate UUID for Idempotency-Key header on each new form submission
- [ ] Show error on insufficient balance / duplicate key
- [ ] Clear form and refresh on success

### 4d. Payout history table
- [ ] Columns: ID, amount, status, created_at
- [ ] Status badge with colour (PENDING=gray, PROCESSING=amber, COMPLETED=green, FAILED=red)
- [ ] Auto-refresh every 5s to show live status changes

**Commit:** `feat: React dashboard — balance, payout form, history table`

---

## Phase 5 — Tests (1 hour)

### 5a. Concurrency test
- [ ] Use `threading.Thread` to fire two simultaneous 60-rupee payout requests for a 100-rupee balance merchant
- [ ] Assert exactly one 201 and one 4xx response
- [ ] Assert final balance = 40 rupees (not 0 or -20)
- [ ] Assert no duplicate LedgerEntry debits

### 5b. Idempotency test
- [ ] POST payout with key `K1` — assert 201
- [ ] POST same payout with key `K1` again — assert same response body and status code
- [ ] Assert only one Payout row created
- [ ] POST with different key `K2` and same amount — assert new payout created

**Commit:** `test: concurrency and idempotency tests`

---

## Phase 6 — Deployment & Polish (1 hour)

- [ ] Write `docker-compose.yml` (postgres, redis, web, worker, beat)
- [ ] Write `README.md` (setup, seed, test instructions)
- [ ] Write `EXPLAINER.md` (see EXPLAINER_TEMPLATE.md)
- [ ] Deploy to Railway or Render
- [ ] Seed production DB
- [ ] Verify live URLs work
- [ ] Submit form

**Commit:** `docs: README, EXPLAINER, docker-compose`

---

## Commit discipline

Make one commit per phase section. Keep messages descriptive. Reviewers read commit history as a signal of how you think.

| Phase | Example message |
|-------|----------------|
| 1a | `feat: Merchant and LedgerEntry models — BigIntegerField amounts` |
| 2c | `feat: POST /payouts with SELECT FOR UPDATE concurrency lock` |
| 3b | `feat: state machine — illegal transitions raise InvalidTransitionError` |
| 5a | `test: concurrent payout requests — exactly one succeeds` |
