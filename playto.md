# Playto Founding Engineer Challenge 2026

> 💳 **About Playto Pay:** Cross-border payment infrastructure for Indian agencies, freelancers, and online businesses who cannot access Stripe or PayPal. Think of us as the Mercury-equivalent for emerging market businesses. [**Learn more at](https://www.playto.so/features/playto-pay) [playto.so/features/playto-pay](http://playto.so/features/playto-pay)**
> 

Role: Founding Engineer. Full-time, Remote, India.
Compensation: 6-10 LPA Fixed plus ESOPs.

## Before you start

You made it past our initial screen. This is the last filter before you meet the CTO and CEO.

We are not looking for a perfect submission. We are looking for someone who thinks like an engineer who has to ship money-moving code to production. Architecture decisions matter more than polish. Correctness matters more than features.

Use any AI tool you want. We care about the quality of thinking, not typing speed. The [EXPLAINER.md](http://EXPLAINER.md) section is where we find out whether you actually understand what you shipped.

## The context

Playto Pay helps Indian agencies and freelancers collect international payments. Money flows in one direction: international customer pays in USD, Playto collects, Playto pays merchant in INR.

The hardest part is not payment collection. It is the payout engine that sits in the middle. Merchants accumulate balance when their customers pay, and they withdraw to their Indian bank account. Your challenge is to build a minimal version of that engine.

## The Playto Payout Engine

Build a service where merchants can see their balance, request payouts, and track payout status. The service must handle the concurrency, idempotency, and data integrity problems that real payment systems fail at.

Stack: Backend is Django plus DRF. Frontend is React plus Tailwind. Database is PostgreSQL, strongly preferred. Background jobs via Celery, Django-Q, or Huey. Do not fake it with sync code.

## Core features

Merchant Ledger. Every merchant has a balance in paise as an integer, never floats. Balance is derived from credits (simulated customer payments) and debits (payouts). Seed 2 to 3 merchants with credit history. You do not need to build the customer payment flow.

Payout Request API. POST to /api/v1/payouts with an idempotency key in the header. Body has amount_paise and bank_account_id. Creates a payout in pending state and holds the funds. Returns the same response if called twice with the same idempotency key.

Payout Processor background worker. Picks up pending payouts and moves them through the lifecycle. Simulate bank settlement: succeed 70 percent, fail 20 percent, hang in processing 10 percent. On success, the payout is final. On failure, the held funds return to the merchant balance.

Merchant Dashboard in React. Shows available balance, held balance, recent credits and debits. Form to request a payout. Table of payout history with live status updates.

## Technical constraints

These are the parts we actually grade you on. Features are easy. These are not.

Money integrity. Amounts stored as BigIntegerField in paise. No FloatField. No DecimalField unless you have a good reason. Balance calculations must use database-level operations, not Python arithmetic on fetched rows. The sum of credits minus debits must always equal the displayed balance. We check this invariant.

Concurrency. A merchant with 100 rupees balance submits two simultaneous 60 rupee payout requests. Exactly one should succeed. The other must be rejected cleanly. Race conditions on check-then-deduct are the most common bug we see.

Idempotency. The Idempotency-Key header is a merchant-supplied UUID. Second call with the same key returns the exact same response as the first. No duplicate payout created. Keys scoped per merchant. Keys expire after 24 hours.

State machine. Legal: pending to processing to completed, OR pending to processing to failed. Illegal (must be rejected): completed to pending, failed to completed, anything backwards. A failed payout returning funds must do so atomically with the state transition.

Retry logic. Payouts stuck in processing for more than 30 seconds should be retried. Exponential backoff, max 3 attempts, then move to failed and return funds.

## AI policy

We want AI-native, not AI-dependent. You should be able to explain every line. You should catch where AI gave you wrong code, especially around transactions, locking, and aggregation. The [EXPLAINER.md](http://EXPLAINER.md) is how we find out whether you shipped code you understand or code you pasted.

## Deliverables

GitHub repository with all code and clean commit history. [README.md](http://README.md) with setup instructions. Seed script to populate merchants. At least 2 meaningful tests, one for concurrency and one for idempotency.

Live deployment anywhere free: Railway, Render, [Fly.io](http://Fly.io), Vercel, Koyeb. Share URL in the form. Seed it with test data.

[EXPLAINER.md](http://EXPLAINER.md) in the repo. Answer these short and specific. This is where most candidates get filtered out.

1. The Ledger. Paste your balance calculation query. Why did you model credits and debits this way?
2. The Lock. Paste the exact code that prevents two concurrent payouts from overdrawing a balance. Explain what database primitive it relies on.
3. The Idempotency. How does your system know it has seen a key before? What happens if the first request is in flight when the second arrives?
4. The State Machine. Where in the code is failed-to-completed blocked? Show the check.
5. The AI Audit. One specific example where AI wrote subtly wrong code (bad locking, wrong aggregation, race condition). Paste what it gave you, what you caught, and what you replaced it with.

Optional bonuses: docker-compose.yml, event sourcing, webhook delivery with retries, audit log. Do not do all of these, just the ones you care about.

## How we evaluate

Clean ledger model tells us you think like someone who will own a money-moving system.

Correct concurrency handling tells us you know the difference between Python-level and database-level locking.

Good idempotency implementation tells us you have shipped an API that deals with real networks.

Sharp [EXPLAINER.md](http://EXPLAINER.md) tells us you understand your own code and will not freeze in a debugging call.

Honest AI audit tells us you are senior enough to not trust the machine blindly.

We are NOT grading on: pixel-perfect UI, perfect test coverage, fancy patterns, feature completeness beyond what is listed.

## What happens after you submit

1. CTO reviews the code and EXPLAINER in 1 to 2 days
2. If shortlisted, 45-minute technical conversation with CTO
3. Final 30-minute chat with CEO
4. Offer within 48 hours of the final chat