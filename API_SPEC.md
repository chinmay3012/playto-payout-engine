# API Specification

Base URL: `/api/v1/`

All responses: `Content-Type: application/json`
All amounts: integers in paise. Never floats.

---

## Endpoints

### GET /api/v1/merchants/
List all merchants (for frontend merchant selector).

**Response 200:**
```json
[
  {
    "id": 1,
    "name": "Acme Exports",
    "email": "acme@example.com"
  }
]
```

---

### GET /api/v1/merchants/{id}/balance/
Returns available, held, and total balance for a merchant.

**Response 200:**
```json
{
  "merchant_id": 1,
  "available_paise": 4000000,
  "held_paise": 500000,
  "total_paise": 4500000,
  "available_inr": "40000.00",
  "held_inr": "5000.00",
  "total_inr": "45000.00"
}
```

Note: `*_inr` fields are strings formatted to 2 decimal places, derived from paise / 100.
These are display-only. All business logic uses paise integers.

---

### GET /api/v1/merchants/{id}/ledger/
Paginated ledger of credits and debits.

**Response 200:**
```json
{
  "count": 42,
  "next": "/api/v1/merchants/1/ledger/?page=2",
  "previous": null,
  "results": [
    {
      "id": 101,
      "entry_type": "CREDIT",
      "amount_paise": 5000000,
      "description": "Payment from client US-001",
      "reference_id": "",
      "created_at": "2024-03-15T10:30:00Z"
    },
    {
      "id": 100,
      "entry_type": "DEBIT",
      "amount_paise": 100000,
      "description": "Payout #PO-55 initiated",
      "reference_id": "55",
      "created_at": "2024-03-14T09:00:00Z"
    }
  ]
}
```

---

### POST /api/v1/payouts/
Create a payout request.

**Required header:**
```
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

**Request body:**
```json
{
  "merchant_id": 1,
  "amount_paise": 100000,
  "bank_account_id": 3
}
```

**Response 201 (new payout created):**
```json
{
  "id": 55,
  "merchant_id": 1,
  "amount_paise": 100000,
  "bank_account_id": 3,
  "status": "PENDING",
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2024-03-15T11:00:00Z"
}
```

**Response 200 (idempotent replay — same key, same response):**
Same body as 201 above. Status code is 200 to distinguish from a fresh creation.

**Response 400 — validation errors:**
```json
{
  "error": "INVALID_REQUEST",
  "detail": "amount_paise must be a positive integer"
}
```

**Response 402 — insufficient balance:**
```json
{
  "error": "INSUFFICIENT_BALANCE",
  "detail": "Available balance 40000 paise is less than requested 100000 paise"
}
```

**Response 409 — idempotency key in flight:**
```json
{
  "error": "KEY_IN_FLIGHT",
  "detail": "A request with this Idempotency-Key is currently being processed. Retry after a moment."
}
```

---

### GET /api/v1/payouts/{id}/
Get single payout detail.

**Response 200:**
```json
{
  "id": 55,
  "merchant_id": 1,
  "amount_paise": 100000,
  "bank_account": {
    "id": 3,
    "account_number": "****1234",
    "ifsc": "HDFC0001234"
  },
  "status": "COMPLETED",
  "attempt_count": 1,
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2024-03-15T11:00:00Z",
  "updated_at": "2024-03-15T11:00:05Z"
}
```

---

### GET /api/v1/merchants/{id}/payouts/
List all payouts for a merchant, newest first.

**Response 200:**
```json
{
  "count": 12,
  "next": null,
  "previous": null,
  "results": [ /* array of payout objects */ ]
}
```

---

## Idempotency behaviour

| Scenario | Expected behaviour |
|----------|--------------------|
| First request with key K | Process normally, store response, return 201 |
| Second request with same key K, same body | Return stored response (same body, 200) |
| Second request with same key K, different body | Return stored response (ignore new body) |
| Request with key K while first is in-flight | Return 409 KEY_IN_FLIGHT |
| Request with key K after 24h | Treat as new request (key expired) |
| Request with key K, different merchant | Treated as new key (keys scoped per merchant) |

---

## Concurrency guarantee

Two simultaneous POST /payouts requests for the same merchant, both requesting more than half the balance:
- Exactly one receives 201
- The other receives 402
- Balance after both requests = original − (amount of the successful one)
- No negative balance ever

This is enforced by `SELECT FOR UPDATE` on a merchant balance lock row inside a `transaction.atomic()` block.

---

## Error codes reference

| Code | HTTP status | Meaning |
|------|-------------|---------|
| `INVALID_REQUEST` | 400 | Missing fields, wrong types, invalid UUID |
| `INVALID_IDEMPOTENCY_KEY` | 400 | Header missing or not a valid UUID |
| `INSUFFICIENT_BALANCE` | 402 | Not enough available balance |
| `MERCHANT_NOT_FOUND` | 404 | Merchant ID does not exist |
| `BANK_ACCOUNT_NOT_FOUND` | 404 | Bank account not found or not owned by merchant |
| `KEY_IN_FLIGHT` | 409 | Idempotency key exists but no response stored yet |
| `INVALID_TRANSITION` | 422 | State machine violation (internal, for debugging) |
