import json

from django.db.models import Sum
from django.test import Client, TestCase

from apps.payouts.models import ApiKey, BankAccount, EntryType, LedgerEntry, Merchant, Payout
from apps.payouts.services import hash_api_key

IDEMPOTENCY_KEY_1 = '550e8400-e29b-41d4-a716-446655440001'
IDEMPOTENCY_KEY_2 = '550e8400-e29b-41d4-a716-446655440002'


class IdempotencyTest(TestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(name='Test', email='t@t.com')
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number='9999999999',
            ifsc='ICIC0009999',
            beneficiary_name='Test',
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            amount_paise=100000,
            entry_type=EntryType.CREDIT,
            description='Setup balance',
            reference_id='',
        )
        self.client = Client()
        self.raw_api_key = 'pk_live_test_merchant_1'
        ApiKey.objects.create(
            merchant=self.merchant,
            name='test key',
            key_prefix=self.raw_api_key[:12],
            hashed_key=hash_api_key(self.raw_api_key),
            scopes=['payouts:write'],
        )

    def _post_payout(self, key, amount=10000):
        return self.client.post(
            '/api/v1/payouts/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'amount_paise': amount,
                    'bank_account_id': self.bank_account.id,
                }
            ),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_X_API_KEY=self.raw_api_key,
        )

    def test_same_key_returns_same_response(self):
        r1 = self._post_payout(IDEMPOTENCY_KEY_1)
        r2 = self._post_payout(IDEMPOTENCY_KEY_1)

        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()['id'], r2.json()['id'])

    def test_same_key_creates_only_one_payout(self):
        self._post_payout(IDEMPOTENCY_KEY_1)
        self._post_payout(IDEMPOTENCY_KEY_1)

        payout_count = Payout.objects.filter(
            merchant=self.merchant,
            idempotency_key=IDEMPOTENCY_KEY_1,
        ).count()
        self.assertEqual(payout_count, 1)

    def test_same_key_creates_only_one_ledger_debit(self):
        self._post_payout(IDEMPOTENCY_KEY_1, amount=5000)
        self._post_payout(IDEMPOTENCY_KEY_1, amount=5000)

        debit_total = LedgerEntry.objects.filter(
            merchant=self.merchant,
            entry_type=EntryType.DEBIT,
        ).aggregate(total=Sum('amount_paise'))['total'] or 0

        self.assertEqual(debit_total, 5000)

    def test_different_key_creates_new_payout(self):
        r1 = self._post_payout(IDEMPOTENCY_KEY_1, amount=5000)
        r2 = self._post_payout(IDEMPOTENCY_KEY_2, amount=5000)

        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])
