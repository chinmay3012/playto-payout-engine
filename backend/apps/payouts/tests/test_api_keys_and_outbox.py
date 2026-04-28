import json
from unittest import mock

from django.test import TestCase

from apps.payouts.models import (
    ApiKey,
    BankAccount,
    EntryType,
    EventOutbox,
    LedgerEntry,
    Merchant,
    WebhookDeliveryAttempt,
)
from apps.payouts.services import dispatch_pending_events, hash_api_key


class ApiKeysAndOutboxTest(TestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(name='Merchant', email='m@example.com')
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number='123412341234',
            ifsc='HDFC0001111',
            beneficiary_name='Merchant',
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            amount_paise=100000,
            entry_type=EntryType.CREDIT,
            description='setup',
            reference_id='',
        )

    def test_create_api_key_endpoint_returns_raw_key_once(self):
        res = self.client.post(
            '/api/v1/api-keys/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'name': 'Server key',
                    'scopes': ['payouts:write'],
                    'expires_in_days': 30,
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertIn('raw_key', body)
        self.assertTrue(body['raw_key'].startswith('pk_live_'))

    @mock.patch('apps.payouts.services.urlrequest.urlopen')
    def test_outbox_dispatch_creates_delivery_attempt(self, mocked_urlopen):
        fake_response = mock.MagicMock()
        fake_response.getcode.return_value = 200
        fake_response.read.return_value = b'ok'
        fake_response.__enter__.return_value = fake_response
        mocked_urlopen.return_value = fake_response

        create_key = self.client.post(
            '/api/v1/api-keys/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'name': 'Server key',
                    'scopes': ['payouts:write'],
                }
            ),
            content_type='application/json',
        ).json()
        raw_key = create_key['raw_key']

        self.client.post(
            '/api/v1/webhook-endpoints/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'url': 'https://example.com/webhook',
                }
            ),
            content_type='application/json',
        )

        payout_res = self.client.post(
            '/api/v1/payouts/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'amount_paise': 5000,
                    'bank_account_id': self.bank_account.id,
                }
            ),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='550e8400-e29b-41d4-a716-446655440011',
            HTTP_X_API_KEY=raw_key,
        )
        self.assertEqual(payout_res.status_code, 201)

        dispatched = dispatch_pending_events()
        self.assertGreaterEqual(dispatched, 1)
        self.assertTrue(EventOutbox.objects.filter(merchant=self.merchant).exists())
        self.assertTrue(WebhookDeliveryAttempt.objects.filter(success=True).exists())
