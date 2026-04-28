# Test Specifications

## test_concurrency.py

**Goal:** Prove that two simultaneous payout requests for the same merchant never overdraw the balance.

```python
# apps/payouts/tests/test_concurrency.py

import threading
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

class ConcurrentPayoutTest(TransactionTestCase):
    """
    Use TransactionTestCase (not TestCase) — regular TestCase wraps each test
    in a transaction that never commits, so SELECT FOR UPDATE behaves differently.
    TransactionTestCase actually commits and rolls back, so the lock works correctly.
    """
    
    def setUp(self):
        # Create a merchant with exactly ₹100 (10000 paise) balance
        self.merchant = Merchant.objects.create(name="Test Merchant", email="test@test.com")
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number="1234567890",
            ifsc="HDFC0001234",
            beneficiary_name="Test Merchant",
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            amount_paise=10000,
            entry_type='CREDIT',
            description='Initial balance',
        )
    
    def test_two_concurrent_60_rupee_requests_from_100_rupee_balance(self):
        """
        Two simultaneous requests for ₹60 each.
        Balance is ₹100. Only one can succeed.
        """
        results = []
        errors  = []
        
        def make_request(key_suffix):
            from django.test import Client
            client = Client()
            response = client.post(
                '/api/v1/payouts/',
                data={
                    'merchant_id': self.merchant.id,
                    'amount_paise': 6000,
                    'bank_account_id': self.bank_account.id,
                },
                content_type='application/json',
                HTTP_IDEMPOTENCY_KEY=f'550e8400-e29b-41d4-a716-{key_suffix:012d}',
            )
            results.append(response.status_code)
        
        t1 = threading.Thread(target=make_request, args=(1,))
        t2 = threading.Thread(target=make_request, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        # Exactly one success, one failure
        self.assertEqual(sorted(results), [201, 402], 
            f"Expected one 201 and one 402, got: {results}")
        
        # Verify balance integrity: exactly 6000 paise debited
        debit_total = LedgerEntry.objects.filter(
            merchant=self.merchant,
            entry_type='DEBIT'
        ).aggregate(total=Sum('amount_paise'))['total'] or 0
        
        self.assertEqual(debit_total, 6000,
            f"Expected exactly 6000 paise debited, got {debit_total}")
        
        # Verify net balance = 4000 paise
        balance = get_merchant_balance(self.merchant.id)
        self.assertGreaterEqual(balance['available_paise'], 0,
            "Balance went negative — overdraft occurred")
    
    def test_balance_never_goes_negative(self):
        """
        Fire 10 concurrent requests, each for ₹20, against ₹100 balance.
        Exactly 5 should succeed. Balance should be ₹0 after all complete.
        """
        results = []
        threads = []
        
        for i in range(10):
            def make_request(i=i):
                from django.test import Client
                c = Client()
                r = c.post(
                    '/api/v1/payouts/',
                    data={'merchant_id': self.merchant.id, 'amount_paise': 2000, 'bank_account_id': self.bank_account.id},
                    content_type='application/json',
                    HTTP_IDEMPOTENCY_KEY=f'550e8400-e29b-41d4-a716-{i:012d}',
                )
                results.append(r.status_code)
            threads.append(threading.Thread(target=make_request))
        
        for t in threads: t.start()
        for t in threads: t.join()
        
        successes = results.count(201)
        failures  = results.count(402)
        
        self.assertEqual(successes, 5, f"Expected 5 successes, got {successes}")
        self.assertEqual(failures, 5,  f"Expected 5 failures, got {failures}")
        
        # Net balance must be 0
        balance = get_merchant_balance(self.merchant.id)
        self.assertEqual(balance['total_paise'], 0)
        self.assertGreaterEqual(balance['available_paise'], 0)
```

---

## test_idempotency.py

**Goal:** Prove the same key returns the same response and creates no duplicate records.

```python
# apps/payouts/tests/test_idempotency.py

from django.test import TestCase
from django.test import Client

IDEMPOTENCY_KEY_1 = '550e8400-e29b-41d4-a716-446655440001'
IDEMPOTENCY_KEY_2 = '550e8400-e29b-41d4-a716-446655440002'

class IdempotencyTest(TestCase):
    
    def setUp(self):
        self.merchant = Merchant.objects.create(name="Test", email="t@t.com")
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number="9999999999",
            ifsc="ICIC0009999",
            beneficiary_name="Test",
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            amount_paise=100000,
            entry_type='CREDIT',
            description='Setup balance',
        )
        self.client = Client()
    
    def _post_payout(self, key, amount=10000):
        return self.client.post(
            '/api/v1/payouts/',
            data={
                'merchant_id': self.merchant.id,
                'amount_paise': amount,
                'bank_account_id': self.bank_account.id,
            },
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key,
        )
    
    def test_same_key_returns_same_response(self):
        r1 = self._post_payout(IDEMPOTENCY_KEY_1)
        r2 = self._post_payout(IDEMPOTENCY_KEY_1)
        
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 200)    # replay returns 200
        self.assertEqual(r1.json()['id'], r2.json()['id'])
    
    def test_same_key_creates_only_one_payout(self):
        self._post_payout(IDEMPOTENCY_KEY_1)
        self._post_payout(IDEMPOTENCY_KEY_1)
        
        payout_count = Payout.objects.filter(
            merchant=self.merchant,
            idempotency_key=IDEMPOTENCY_KEY_1,
        ).count()
        
        self.assertEqual(payout_count, 1, "Duplicate payout was created")
    
    def test_same_key_creates_only_one_ledger_debit(self):
        self._post_payout(IDEMPOTENCY_KEY_1, amount=5000)
        self._post_payout(IDEMPOTENCY_KEY_1, amount=5000)
        
        debit_total = LedgerEntry.objects.filter(
            merchant=self.merchant,
            entry_type='DEBIT',
        ).aggregate(total=Sum('amount_paise'))['total'] or 0
        
        self.assertEqual(debit_total, 5000, "Balance was debited twice")
    
    def test_different_key_creates_new_payout(self):
        r1 = self._post_payout(IDEMPOTENCY_KEY_1, amount=5000)
        r2 = self._post_payout(IDEMPOTENCY_KEY_2, amount=5000)
        
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])
    
    def test_key_scoped_per_merchant(self):
        """Same key for different merchants creates two separate payouts."""
        merchant2 = Merchant.objects.create(name="Other", email="other@t.com")
        bank2 = BankAccount.objects.create(
            merchant=merchant2,
            account_number="1111111111",
            ifsc="SBIN0001111",
            beneficiary_name="Other",
        )
        LedgerEntry.objects.create(
            merchant=merchant2, amount_paise=100000, entry_type='CREDIT', description='Setup'
        )
        
        r1 = self._post_payout(IDEMPOTENCY_KEY_1)
        r2 = self.client.post(
            '/api/v1/payouts/',
            data={'merchant_id': merchant2.id, 'amount_paise': 10000, 'bank_account_id': bank2.id},
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=IDEMPOTENCY_KEY_1,  # same key, different merchant
        )
        
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])
```

---

## Running

```bash
# Must use TransactionTestCase for concurrency tests
python manage.py test apps.payouts.tests.test_concurrency --verbosity=2
python manage.py test apps.payouts.tests.test_idempotency --verbosity=2
```

**Note on test DB:** Django creates a separate test database. The `TransactionTestCase` actually commits transactions (unlike `TestCase`), so `SELECT FOR UPDATE` locking works correctly in concurrency tests.
