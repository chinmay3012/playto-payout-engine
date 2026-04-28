# Demo Checklist (Reviewer Friendly)

Use this flow to verify the graded behaviors in under 2 minutes.

## Pre-check

- Backend server running on `:8000`
- Celery worker running
- Celery beat running
- Frontend running

## Steps

1. Login with demo credentials (`demo_owner` / `StrongPass123`).
2. Select merchant `Acme Exports`.
3. Confirm balance card shows:
   - Available
   - Held
   - Total (`Available + Held`)
4. Open payout form:
   - choose seeded bank account
   - submit a small payout (e.g. INR 100)
5. Observe payout table auto-refresh (5s) and status movement:
   - `PENDING -> PROCESSING -> COMPLETED` or `FAILED`
6. If status is `FAILED`, confirm refund behavior:
   - a compensating `CREDIT` appears in ledger
   - total money integrity remains consistent

## Fast API sanity checks

```bash
curl http://localhost:8000/api/v1/merchants/1/balance/
curl http://localhost:8000/api/v1/merchants/1/payouts/
curl http://localhost:8000/api/v1/merchants/1/ledger/
```

## What this demonstrates

- DB-aggregated ledger balance in paise (money integrity)
- Concurrent-safe payout creation path (via DB locking)
- Idempotent payout API behavior
- Strict payout state machine
- Atomic fund return on failed payout
- Live payout status updates in UI
