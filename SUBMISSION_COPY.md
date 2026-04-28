# Submission Form Copy

## Project summary

I built a minimal payout engine for merchant withdrawals with production-critical guarantees around:

- money integrity via append-only ledger in paise (integer amounts),
- concurrency safety during payout creation,
- idempotent payout API behavior,
- strict payout lifecycle state machine,
- async payout processing with retries for stuck processing states.

Frontend includes a modern dashboard for merchant balance, payout requests, live payout status updates, and ledger visibility.

## Architecture highlights

- Ledger-first accounting model: no mutable balance column.
- `SELECT ... FOR UPDATE` + transactional payout creation to prevent overspend races.
- Idempotency keys scoped per merchant with replay of stored response and in-flight protection.
- Worker-driven payout processing (`PENDING -> PROCESSING -> COMPLETED/FAILED`) with retry scheduling for stuck processing payouts.
- Failed payouts return funds atomically by state transition + compensating credit.

## What I am most proud of

I prioritized correctness over feature breadth and focused on the exact failure modes money systems face: race conditions, duplicate requests, and invalid state transitions. The project is intentionally centered on correctness primitives that make payout systems safe.

## How to run locally

See `README.md` for full setup.

Quick version:

1. `python3 backend/manage.py migrate && python3 backend/manage.py seed`
2. Run backend server (`:8000`)
3. Run Celery worker + beat
4. Run frontend (`npm run dev`)

## Reviewer demo path

See `DEMO_CHECKLIST.md` for a 2-minute validation flow.

## Live URL

`<PASTE_DEPLOYMENT_URL_HERE>`

## Repository URL

`<PASTE_GITHUB_REPO_URL_HERE>`
