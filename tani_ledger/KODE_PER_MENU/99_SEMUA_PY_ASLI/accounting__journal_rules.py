"""Aturan jurnal umum otomatis.

Admin hanya mengisi keterangan + satu nominal. Modul ini menentukan akun debet/kredit
dari kata kunci pada keterangan, menghitung diskon/termin, dan menghasilkan baris
jurnal yang selalu seimbang. Dipakai bersama oleh halaman simpan dan pratinjau live,
sehingga yang terlihat di layar persis sama dengan yang diposting.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from .models import Account, JournalEntry, Party, Product, ZERO
from .services import money

# Akun retur dan potongan (kontra). Dibuat oleh `seed_agriculture`.
SALES_RETURN = '4130'
SALES_DISCOUNT = '4140'
PURCHASE_RETURN = '5120'
PURCHASE_DISCOUNT = '5130'

TERM_SUGGESTIONS = ['n/30', 'n/60', '2/10,n/30', '1/10,n/30', '2/10,n/60']
_TERM_RE = re.compile(r'^(?:(?P<pct>\d+(?:[.,]\d+)?)/(?P<days>\d+)\s*,\s*)?n/(?P<net>\d+)$', re.I)

BANK_WORDS = ('bank', 'transfer', 'rekening')
CASH_WORDS = ('tunai', 'cash', 'kas')
CREDIT_WORDS = (' kredit', 'utang', 'piutang')


@dataclass
class Term:
    text: str
    discount_pct: Decimal | None
    discount_days: int | None
    net_days: int


@dataclass
class JournalPlan:
    type: str
    lines: list = field(default_factory=list)  # {'account','party','debit','credit'}
    discount: Decimal = ZERO
    term: Term | None = None
    due_date: date | None = None

    @property
    def total_debit(self):
        return sum((x['debit'] for x in self.lines), ZERO)

    @property
    def total_credit(self):
        return sum((x['credit'] for x in self.lines), ZERO)


def parse_term(text):
    """'2/10,n/30' -> diskon 2% jika lunas ≤10 hari, jatuh tempo 30 hari. 'n/30' tanpa diskon."""
    text = (text or '').strip()
    if not text:
        return None
    m = _TERM_RE.match(text.replace(' ', ''))
    if not m:
        raise ValidationError('Format termin tidak dikenali. Contoh: n/30 atau 2/10,n/30.')
    pct = Decimal(m['pct'].replace(',', '.')) if m['pct'] else None
    if pct is not None and not (ZERO < pct < 100):
        raise ValidationError('Persen diskon termin harus di antara 0 dan 100.')
    days = int(m['days']) if m['days'] else None
    net = int(m['net'])
    if net <= 0 or (days is not None and days >= net):
        raise ValidationError('Masa diskon harus lebih pendek daripada jatuh tempo (contoh 2/10,n/30).')
    clean = f'{m["pct"]}/{days},n/{net}' if pct is not None else f'n/{net}'
    return Term(clean, pct, days, net)


def next_reference(entry_date):
    """Nomor bukti berikutnya yang pasti belum dipakai (aman setelah jurnal dihapus)."""
    prefix = f'JU-{entry_date:%Y%m%d}-'
    used = set(JournalEntry.objects.filter(date=entry_date, reference__startswith=prefix)
               .values_list('reference', flat=True))
    n = 1
    while f'{prefix}{n:03d}' in used:
        n += 1
    return f'{prefix}{n:03d}'


def _account(code):
    account = Account.objects.filter(code=code, is_active=True, is_header=False).first()
    if not account:
        raise ValidationError(
            f'Akun {code} belum tersedia atau tidak aktif. Tambahkan di Daftar Akun '
            f'atau jalankan: python manage.py seed_agriculture')
    return account


def _party_for(kind, description):
    parties = list(Party.objects.filter(kind=kind))
    label = 'pelanggan' if kind == Party.Kind.CUSTOMER else 'pemasok'
    normalized = description.casefold()
    matched = [p for p in parties if p.name.casefold() in normalized or p.code.casefold() in normalized]
    if len(matched) == 1:
        return matched[0]
    if len(parties) == 1:
        return parties[0]
    if parties:
        raise ValidationError(f'Keterangan harus memuat nama/kode {label} agar relasi akun dapat ditentukan otomatis.')
    raise ValidationError(f'Daftar {label} belum tersedia. Tambahkan dahulu di Kode Pembantu (/parties/).')


def _has(text, words):
    return any(w in text for w in words)


def resolve_general_journal(description):
    """Kembalikan (jenis, kode_debet, kode_kredit) dari kata kunci. Tidak menebak frasa ambigu."""
    text = ' ' + ' '.join(description.casefold().replace('-', ' ').split()) + ' '
    products = [p for p in Product.objects.all()]
    product_named = any(p.name.casefold() in text or p.code.casefold() in text for p in products)

    def bank_or_cash(default_error):
        if _has(text, BANK_WORDS):
            return '1110'
        if _has(text, CASH_WORDS):
            return '1120'
        raise ValidationError(default_error)

    def purchase_settlement():
        if _has(text, (' kredit', 'utang')):
            return '2110'
        return bank_or_cash('Tambahkan cara pembayaran pada keterangan: tunai, transfer/bank, atau kredit.')

    def sale_settlement():
        if _has(text, (' kredit', 'piutang')):
            return '1140'
        return bank_or_cash('Untuk penjualan, tuliskan apakah tunai, transfer/bank, atau kredit.')

    def cash_or_bank():
        return '1110' if _has(text, BANK_WORDS) else '1120'

    buying = _has(text, ('beli', 'pembelian'))
    selling_words = _has(text, ('penjualan', 'menjual', 'jual hasil tani'))
    product_words = _has(text, ('hasil tani', 'produk', 'barang', 'panen', 'bibit', 'pupuk', 'kompos',
                                'penyemprot', 'hama')) or product_named

    # Retur harus diperiksa lebih dulu karena kalimatnya memuat kata "penjualan"/"pembelian".
    if _has(text, ('retur penjualan', 'retur jual')):
        return 'sale_return', SALES_RETURN, sale_settlement()
    if _has(text, ('retur pembelian', 'retur beli')):
        return 'purchase_return', purchase_settlement(), PURCHASE_RETURN
    # Pembelian persediaan: kata kunci eksplisit, bibit/penyemprot, atau nama produk terdaftar.
    if buying and (_has(text, ('persediaan', 'hasil tani', 'bibit', 'penyemprot')) or product_named):
        return 'purchase', '1150', purchase_settlement()
    if _has(text, ('pupuk', 'pestisida')) and buying:
        return 'purchase', '6110', purchase_settlement()
    if _has(text, ('perlengkapan pertanian', 'alat pertanian habis pakai')) and buying:
        return 'purchase', '1160', purchase_settlement()
    if selling_words and product_words:
        return 'sale', sale_settlement(), '4110'
    if _has(text, ('penerimaan piutang', 'terima piutang', 'pelunasan piutang')):
        return 'receipt', cash_or_bank(), '1140'
    if _has(text, ('pembayaran utang', 'bayar utang', 'pelunasan utang')):
        return 'payment', '2110', cash_or_bank()
    if _has(text, ('listrik', ' air ')) and _has(text, ('bayar', 'pembayaran', 'tagihan')):
        return 'other', '6130', purchase_settlement()
    if _has(text, ('transportasi', 'ongkos angkut', 'biaya angkut')):
        return 'other', '6140', purchase_settlement()
    if _has(text, ('gaji', 'upah', 'tenaga kerja')) and _has(text, ('bayar', 'pembayaran', 'upah')):
        return 'other', '6120', purchase_settlement()
    if _has(text, ('setoran modal', 'modal disetor', 'tambahan modal')):
        return 'other', cash_or_bank(), '3100'
    if _has(text, ('pendapatan jasa', 'penerimaan jasa')):
        return 'other', cash_or_bank(), '4120'
    if _has(text, ('pendapatan lain', 'penerimaan lain')):
        return 'other', cash_or_bank(), '7110'
    if _has(text, ('beban bunga', 'bayar bunga')):
        return 'other', '8120', purchase_settlement()
    raise ValidationError(
        'Jenis transaksi belum dikenali. Tambahkan kata kunci yang jelas, misalnya '
        '"pembelian pupuk tunai", "penjualan hasil tani kredit", "retur penjualan tunai" '
        'atau "pembayaran listrik".')


def build_general_journal(description, amount, entry_date, *, term_text='', discount_percent=None,
                          discount_rp=None, use_term_discount=False):
    """Susun baris jurnal. `amount` boleh nol (untuk pratinjau sebelum nominal diisi)."""
    amount = money(amount or 0)
    kind, debit_code, credit_code = resolve_general_journal(description)
    debit_account, credit_account = _account(debit_code), _account(credit_code)
    debit_party = credit_party = None
    if debit_code == '1140':
        debit_party = _party_for(Party.Kind.CUSTOMER, description)
    if credit_code == '1140':
        credit_party = _party_for(Party.Kind.CUSTOMER, description)
    if debit_code == '2110':
        debit_party = _party_for(Party.Kind.SUPPLIER, description)
    if credit_code == '2110':
        credit_party = _party_for(Party.Kind.SUPPLIER, description)

    term = parse_term(term_text)
    pct = Decimal(discount_percent) if discount_percent else None
    rp = money(discount_rp) if discount_rp else None
    wants_discount = bool((pct and pct > 0) or (rp and rp > 0) or use_term_discount)
    credit_settlement = kind in ('sale', 'purchase') and (debit_code == '1140' or credit_code == '2110')

    if pct and rp:
        raise ValidationError('Isi diskon dalam persen ATAU rupiah, tidak keduanya.')
    if pct is not None and not (ZERO <= pct < 100):
        raise ValidationError('Diskon persen harus di antara 0 dan kurang dari 100.')
    if wants_discount and kind not in ('sale', 'purchase', 'receipt', 'payment'):
        raise ValidationError('Diskon hanya berlaku untuk penjualan, pembelian, penerimaan piutang, dan pembayaran utang.')
    if term:
        if kind in ('sale', 'purchase') and not credit_settlement:
            raise ValidationError('Termin hanya berlaku untuk transaksi kredit. Tambahkan kata "kredit" pada keterangan.')
        if kind not in ('sale', 'purchase', 'receipt', 'payment'):
            raise ValidationError('Termin hanya berlaku untuk penjualan/pembelian kredit, penerimaan piutang, atau pembayaran utang.')
    if use_term_discount:
        if not term or term.discount_pct is None:
            raise ValidationError('Pilih termin yang memuat diskon (contoh 2/10,n/30) untuk memakai potongan termin.')
        if kind in ('sale', 'purchase'):
            raise ValidationError('Potongan termin diambil saat pelunasan: gunakan "penerimaan piutang" atau "pembayaran utang".')
        if pct or rp:
            raise ValidationError('Potongan termin tidak dapat digabung dengan diskon manual.')
        pct = term.discount_pct

    discount = ZERO
    if wants_discount:
        discount = rp if rp else money(amount * pct / 100)
        if amount > 0 and not (ZERO < discount < amount):
            raise ValidationError('Diskon harus lebih besar dari nol dan lebih kecil daripada nominal transaksi.')

    def line(account, party=None, debit=ZERO, credit=ZERO):
        return {'account': account, 'party': party, 'debit': debit, 'credit': credit}

    if wants_discount and kind in ('sale', 'receipt'):
        # Kas/piutang berkurang sebesar diskon; potongan penjualan dicatat tersendiri (metode bruto).
        lines = [line(debit_account, debit_party, debit=amount - discount),
                 line(_account(SALES_DISCOUNT), debit=discount),
                 line(credit_account, credit_party, credit=amount)]
    elif wants_discount:
        lines = [line(debit_account, debit_party, debit=amount),
                 line(credit_account, credit_party, credit=amount - discount),
                 line(_account(PURCHASE_DISCOUNT), credit=discount)]
    else:
        lines = [line(debit_account, debit_party, debit=amount),
                 line(credit_account, credit_party, credit=amount)]

    due = entry_date + timedelta(days=term.net_days) if term and credit_settlement and entry_date else None
    return JournalPlan(type=kind, lines=lines, discount=discount, term=term, due_date=due)
