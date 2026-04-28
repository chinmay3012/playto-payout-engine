# Playto Payout Engine

Cross-border payout infrastructure for Indian merchants. Merchants accumulate USD balance and withdraw to Indian bank accounts via a ledger-based payout engine.

**Live demo:** [your-deployment-url]

---

## Tech stack

- **Backend:** Django 4.2 + Django REST Framework
- **Frontend:** React 18 + Vite + Tailwind CSS
- **Database:** PostgreSQL 15
- **Task queue:** Celery + Redis
- **Deployment:** Railway (or Render / Fly.io)

---

## Local setup

### Prerequisites
- Python 3.11+
- Node 18+
- PostgreSQL 15+
- Redis 7+

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your local DB and Redis URLs

python manage.py migrate
python manage.py seed          # populates 3 merchants with credit history
python manage.py runserver     # http://localhost:8000
```

**Start Celery worker (separate terminal):**
```bash
cd backend
celery -A config worker --loglevel=info
```

**Start Celery beat (separate terminal):**
```bash
cd backend
celery -A config beat --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

---

## Running tests

```bash
cd backend
python manage.py test apps.payouts.tests

# Or individually:
python manage.py test apps.payouts.tests.test_concurrency
python manage.py test apps.payouts.tests.test_idempotency
```

---

## Docker (optional)

```bash
docker-compose up --build
docker-compose exec web python manage.py seed
```

Services:
- Web (Django): http://localhost:8000
- Frontend (React): http://localhost:5173
- PostgreSQL: localhost:5432
- Redis: localhost:6379

---

## Architecture decisions

See [EXPLAINER.md](./EXPLAINER.md) for detailed reasoning on ledger design, concurrency locking, idempotency, and the state machine.

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/merchants/` | List merchants |
| GET | `/api/v1/merchants/{id}/balance/` | Available and held balance |
| GET | `/api/v1/merchants/{id}/ledger/` | Credit/debit history |
| POST | `/api/v1/payouts/` | Create payout request |
| GET | `/api/v1/payouts/{id}/` | Payout detail |
| GET | `/api/v1/merchants/{id}/payouts/` | Payout history |

All amounts are integers in paise. POST /payouts requires `Idempotency-Key: <UUID>` header.

---

## What I'm most proud of

[Fill this in — the submission form asks for it too]
