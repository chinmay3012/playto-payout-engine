from django.core.management.base import BaseCommand

from apps.payouts.models import BankAccount, EntryType, LedgerEntry, Merchant
from apps.payouts.services import get_merchant_balance


class Command(BaseCommand):
    help = 'Seed merchants, bank accounts, and credit history'

    def handle(self, *args, **options):
        merchants = [
            {
                'name': 'Acme Exports',
                'email': 'acme@example.com',
                'account_number': '12345678901234',
                'ifsc': 'HDFC0001234',
                'beneficiary_name': 'Acme Exports',
                'credits': [
                    (5000000, 'Initial payment from client US-001'),
                    (3500000, 'Invoice #INV-2024-001 settled'),
                    (1500000, 'Retainer for March 2024'),
                ],
            },
            {
                'name': 'Nova Freelance Studio',
                'email': 'nova@example.com',
                'account_number': '98765432105678',
                'ifsc': 'ICIC0005678',
                'beneficiary_name': 'Nova Freelance Studio',
                'credits': [
                    (7500000, 'Project Phoenix milestone 1'),
                    (2500000, 'Consulting fee - Q1'),
                ],
            },
            {
                'name': 'Bright Digital Agency',
                'email': 'bright@example.com',
                'account_number': '11223344559012',
                'ifsc': 'SBIN0009012',
                'beneficiary_name': 'Bright Digital Agency',
                'credits': [
                    (20000000, 'Retainer contract - 6 months'),
                    (5000000, 'Ad campaign management fee'),
                ],
            },
        ]

        for item in merchants:
            merchant, _ = Merchant.objects.get_or_create(
                email=item['email'], defaults={'name': item['name']}
            )
            BankAccount.objects.get_or_create(
                merchant=merchant,
                account_number=item['account_number'],
                ifsc=item['ifsc'],
                defaults={
                    'beneficiary_name': item['beneficiary_name'],
                    'is_active': True,
                },
            )

            for amount_paise, description in item['credits']:
                LedgerEntry.objects.get_or_create(
                    merchant=merchant,
                    amount_paise=amount_paise,
                    entry_type=EntryType.CREDIT,
                    description=description,
                    defaults={'reference_id': ''},
                )

        self.stdout.write(self.style.SUCCESS('Seed complete'))
        for merchant in Merchant.objects.all().order_by('id'):
            balance = get_merchant_balance(merchant.id)
            self.stdout.write(
                f"- {merchant.name}: {balance['total_paise']} paise (held {balance['held_paise']})"
            )
