import json

from django.test import TestCase

from apps.payouts.models import ApiKey, BankAccount, EntryType, LedgerEntry, Merchant
from apps.payouts.services import hash_api_key


class AuthAndRiskTest(TestCase):
    def setUp(self):
        self.client.defaults['CONTENT_TYPE'] = 'application/json'
        self.merchant = Merchant.objects.create(name='Risk Merchant', email='risk@example.com')
        self.bank = BankAccount.objects.create(
            merchant=self.merchant,
            account_number='123123123123',
            ifsc='HDFC0009999',
            beneficiary_name='Risk Merchant',
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            amount_paise=500000,
            entry_type=EntryType.CREDIT,
            description='seed',
            reference_id='',
        )
        self.raw_key = 'pk_live_risk_scope_key'
        ApiKey.objects.create(
            merchant=self.merchant,
            name='risk key',
            key_prefix=self.raw_key[:12],
            hashed_key=hash_api_key(self.raw_key),
            scopes=['payouts:write'],
        )

    def test_auth_register_and_login(self):
        reg = self.client.post(
            '/api/v1/auth/register/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'username': 'owner1',
                    'email': 'owner1@example.com',
                    'password': 'StrongPass123',
                    'role': 'OWNER',
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(reg.status_code, 201)

        login = self.client.post(
            '/api/v1/auth/login/',
            data=json.dumps({'username': 'owner1', 'password': 'StrongPass123'}),
            content_type='application/json',
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn('playto_access', login.cookies)
        self.assertIn('playto_refresh', login.cookies)

        me = self.client.get('/api/v1/auth/me/')
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()['username'], 'owner1')

        refresh = self.client.post('/api/v1/auth/refresh/', data='{}', content_type='application/json')
        self.assertEqual(refresh.status_code, 200)
        self.assertIn('playto_access', refresh.cookies)

    def test_risk_limit_blocks_large_payout(self):
        self.client.post(
            '/api/v1/auth/register/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'username': 'owner2',
                    'email': 'owner2@example.com',
                    'password': 'StrongPass123',
                    'role': 'OWNER',
                }
            ),
            content_type='application/json',
        )
        self.client.post(
            '/api/v1/auth/login/',
            data=json.dumps({'username': 'owner2', 'password': 'StrongPass123'}),
            content_type='application/json',
        )

        self.client.patch(
            f'/api/v1/merchants/{self.merchant.id}/risk-profile/',
            data=json.dumps({'max_single_payout_paise': 1000}),
            content_type='application/json',
        )

        payout = self.client.post(
            '/api/v1/payouts/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'amount_paise': 5000,
                    'bank_account_id': self.bank.id,
                }
            ),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='550e8400-e29b-41d4-a716-446655440099',
            HTTP_X_API_KEY=self.raw_key,
        )
        self.assertEqual(payout.status_code, 429)
        self.assertEqual(payout.json()['error'], 'RISK_RULE_VIOLATION')

    def test_account_profile_and_password_change(self):
        self.client.post(
            '/api/v1/auth/register/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'username': 'operator1',
                    'email': 'operator1@example.com',
                    'password': 'StrongPass123',
                    'role': 'OPERATOR',
                }
            ),
            content_type='application/json',
        )
        self.client.post(
            '/api/v1/auth/login/',
            data=json.dumps({'username': 'operator1', 'password': 'StrongPass123'}),
            content_type='application/json',
        )

        profile = self.client.patch(
            '/api/v1/account/profile/',
            data=json.dumps({'username': 'operator1_updated', 'email': 'new@example.com'}),
            content_type='application/json',
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()['username'], 'operator1_updated')

        change = self.client.post(
            '/api/v1/account/change-password/',
            data=json.dumps({'current_password': 'StrongPass123', 'new_password': 'StrongerPass456'}),
            content_type='application/json',
        )
        self.assertEqual(change.status_code, 200)

    def test_role_protected_sections(self):
        self.client.post(
            '/api/v1/auth/register/',
            data=json.dumps(
                {
                    'merchant_id': self.merchant.id,
                    'username': 'operator2',
                    'email': 'operator2@example.com',
                    'password': 'StrongPass123',
                    'role': 'OPERATOR',
                }
            ),
            content_type='application/json',
        )
        login = self.client.post(
            '/api/v1/auth/login/',
            data=json.dumps({'username': 'operator2', 'password': 'StrongPass123'}),
            content_type='application/json',
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get('/api/v1/operator/home/').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/admin/home/').status_code, 403)
