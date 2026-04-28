# Playto Payout Engine

Minimal payout engine for merchant withdrawals with strong guarantees around money integrity, concurrency, idempotency, and payout state transitions.

## What this solves

- Merchants can view derived balance from an append-only ledger.
- Merchants can request payouts to linked Indian bank accounts.
- Payouts process asynchronously through a worker with simulated outcomes.
- Failed payouts atomically return funds via compensating ledger credits.

## Stack

- Backend: Django + DRF
- Frontend: React + Vite + Tailwind
- Queue: Celery + Celery Beat
- Local DB/Broker: SQLite (for fast local setup)

## Quickstart (2-3 minutes)

### 1) Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

python3 backend/manage.py migrate
python3 backend/manage.py seed
python3 backend/manage.py runserver 0.0.0.0:8000
```

### 2) Worker + Beat (separate terminals)

```bash
cd backend
python3 -m celery -A config.celery:app worker --loglevel=info --pool=solo
```

```bash
cd backend
python3 -m celery -A config.celery:app beat --loglevel=info
```

### 3) Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the frontend URL shown by Vite (typically `http://localhost:5173` or next free port).

## Demo account

Create once from the Register page:

- Merchant ID: `1`
- Username: `demo_owner`
- Email: `demo_owner@example.com`
- Password: `StrongPass123`
- Role: `OWNER`

Then login using:

- Username: `demo_owner`
- Password: `StrongPass123`

## Core API endpoints

- `GET /api/v1/merchants/`
- `GET /api/v1/merchants/{id}/balance/`
- `GET /api/v1/merchants/{id}/ledger/`
- `GET /api/v1/merchants/{id}/bank-accounts/`
- `POST /api/v1/payouts/` (requires `Idempotency-Key` header)
- `GET /api/v1/payouts/{id}/`
- `GET /api/v1/merchants/{id}/payouts/`

## Tests

Run full payouts test suite:

```bash
python3 backend/manage.py test apps.payouts.tests
```

Run graded tests directly:

```bash
python3 backend/manage.py test apps.payouts.tests.test_concurrency apps.payouts.tests.test_idempotency
```

## Submission notes

- Detailed engineering reasoning is in `EXPLAINER.md`.
- Reviewer walk-through is in `DEMO_CHECKLIST.md`.
- Ready-to-paste form text is in `SUBMISSION_COPY.md`.
