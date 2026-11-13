from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from accounting.models import Account, Product
from accounting.services import create_opening_stock, money

# (kode, nama, satuan, jumlah, harga pokok per satuan, harga jual standar per satuan)
PRODUK = [
    ('BIBIT-01', 'Bibit Tanaman', 'bibit', Decimal('2000'), Decimal('250'), Decimal('400')),      # total Rp500.000
    ('PPK-KOM', 'Pupuk Kompos', 'kg', Decimal('100'), Decimal('10000'), Decimal('14000')),
    ('SPR-HAMA', 'Penyemprot Hama', 'pcs', Decimal('15'), Decimal('150000'), Decimal('200000')),
]


class Command(BaseCommand):
    help = ('Tambah produk bibit, pupuk kompos, dan penyemprot hama beserta stok awal FIFO. '
            'Aman dijalankan ulang: produk yang sudah ada dilewati.')

    def add_arguments(self, parser):
        parser.add_argument('--tanggal', help='Tanggal saldo awal (YYYY-MM-DD), default hari ini.')

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            opening_date = date.fromisoformat(options['tanggal']) if options['tanggal'] else timezone.localdate()
        except ValueError:
            raise CommandError('Format --tanggal harus YYYY-MM-DD.')
        try:
            inventory = Account.objects.get(code='1150')
            equity = Account.objects.get(code='3100')
        except Account.DoesNotExist:
            raise CommandError('Akun 1150 dan 3100 belum ada. Jalankan dulu: python manage.py seed_agriculture')
        added = Decimal('0')
        for code, name, unit, qty, cost, price in PRODUK:
            if Product.objects.filter(code=code).exists():
                self.stdout.write(f'Lewati {code}: sudah ada.')
                continue
            product = Product.objects.create(code=code, name=name, unit=unit, sale_price=price)
            create_opening_stock(product, qty, cost, opening_date)
            value = money(qty * cost)
            added += value
            self.stdout.write(f'+ {code} {name}: {qty:,.0f} {unit} × Rp{cost:,.0f} = Rp{value:,.0f}')
        if added:
            # Saldo awal persediaan di neraca harus sama dengan nilai kartu stok; lawannya modal pemilik.
            inventory.opening_balance += added
            equity.opening_balance += added
            inventory.save(update_fields=['opening_balance'])
            equity.save(update_fields=['opening_balance'])
        self.stdout.write(self.style.SUCCESS(
            f'Selesai. Persediaan awal bertambah Rp{added:,.0f} (akun 1150 didebet, 3100 Modal Pemilik dikredit).'))
