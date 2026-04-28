import json
import threading
import uuid

from django.db.models import Sum
from django.test import Client, TransactionTestCase

from apps.payouts.models import ApiKey, BankAccount, EntryType, LedgerEntry, Merchant
from apps.payouts.services import get_merchant_balance
from apps.payouts.services import hash_api_key


class ConcurrentPayoutTest(TransactionTestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(name='Test Merchant', email='test@test.com')
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number='1234567890',
            ifsc='HDFC0001234',
            beneficiary_name='Test Merchant',
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            amount_paise=10000,
            entry_type=EntryType.CREDIT,
            description='Initial balance',
            reference_id='',
        )
        self.raw_api_key = 'pk_live_concurrency_test_key'
        ApiKey.objects.create(
            merchant=self.merchant,
            name='concurrency key',
            key_prefix=self.raw_api_key[:12],
            hashed_key=hash_api_key(self.raw_api_key),
            scopes=['payouts:write'],
        )

    def _post(self, amount_paise, key):
        client = Client()
        client.raise_request_exception = False
        return client.post(
            '/api/v1/payouts/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'amount_paise': amount_paise,
                    'bank_account_id': self.bank_account.id,
                }
            ),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=str(key),
            HTTP_X_API_KEY=self.raw_api_key,
        )

    def test_two_concurrent_60_rupee_requests_from_100_rupee_balance(self):
        results = []

        def make_request(key):
            res = self._post(6000, key)
            results.append(res.status_code)

        t1 = threading.Thread(target=make_request, args=(uuid.uuid4(),))
        t2 = threading.Thread(target=make_request, args=(uuid.uuid4(),))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(results), 2)
        self.assertEqual(results.count(201), 1)
        self.assertEqual(
            results.count(402) + results.count(409),
            1,
            f'Expected one rejection (402/409), got {results}',
        )

        debit_total = LedgerEntry.objects.filter(
            merchant=self.merchant,
            entry_type=EntryType.DEBIT,
        ).aggregate(total=Sum('amount_paise'))['total'] or 0
        self.assertEqual(debit_total, 6000)

        balance = get_merchant_balance(self.merchant.id)
        self.assertEqual(balance['total_paise'], 4000)
        self.assertGreaterEqual(balance['available_paise'], 0)
