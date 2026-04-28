# Project Structure

```
playto-payout-engine/
│
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   │
│   ├── config/                        # Django project settings
│   │   ├── __init__.py
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── local.py
│   │   │   └── production.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── celery.py                  # Celery app initialisation
│   │
│   └── apps/
│       └── payouts/                   # Single Django app — keep it simple
│           ├── __init__.py
│           ├── models.py              # All models here
│           ├── serializers.py
│           ├── views.py               # DRF ViewSets / APIViews
│           ├── urls.py
│           ├── tasks.py               # Celery tasks
│           ├── services.py            # Business logic (payout processing, state machine)
│           ├── exceptions.py          # Custom exceptions (InvalidTransitionError, etc.)
│           ├── admin.py
│           └── tests/
│               ├── __init__.py
│               ├── test_concurrency.py
│               └── test_idempotency.py
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api/
│       │   └── client.js              # Axios instance + API functions
│       └── components/
│           ├── BalanceCard.jsx
│           ├── LedgerTable.jsx
│           ├── PayoutForm.jsx
│           └── PayoutHistory.jsx
│
├── docker-compose.yml
├── README.md
└── EXPLAINER.md
```

---

## Key file responsibilities

### `models.py`
All four models live here: `Merchant`, `LedgerEntry`, `Payout`, `IdempotencyKey`.
Keep models thin — no business logic in model methods.

### `services.py`
This is where the real work happens:
- `get_merchant_balance(merchant_id)` — DB aggregate, returns dict
- `create_payout_request(merchant, amount_paise, bank_account, idempotency_key)` — the locked transaction
- `process_payout(payout_id)` — called by Celery task
- `transition_payout_status(payout, new_status)` — enforces state machine
- `return_funds(payout)` — atomic: creates CREDIT + sets status=FAILED

### `tasks.py`
Thin wrappers over services:
- `process_payout_task(payout_id)` — calls `services.process_payout`
- `retry_stuck_payouts()` — periodic beat task, finds stuck ones

### `views.py`
Request/response handling only. No business logic here. Call services.

### `serializers.py`
- `PayoutSerializer`
- `LedgerEntrySerializer`
- `BalanceSerializer`

---

## Environment variables (.env.example)

```env
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/playto_payouts

# Redis / Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# App
FRONTEND_URL=http://localhost:5173
```
