from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone
from .models import Account, BusinessProfile, InventoryMovement, JournalEntry, JournalLine, Party, Product


class StyledMixin:
    def style_fields(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'check-input')
            else:
                field.widget.attrs.setdefault('class', 'form-control')


class AccountForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Account
        fields = ('code', 'name', 'category', 'normal_balance', 'opening_balance', 'is_header', 'is_active')
        widgets = {'code': forms.TextInput(attrs={'placeholder': 'Contoh: 1110'}),
                   'name': forms.TextInput(attrs={'placeholder': 'Contoh: Kas di Bank'})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()
    def clean(self):
        data = super().clean()
        if self.instance.pk and self.instance.journalline_set.exists():
            for key in ('code', 'category', 'normal_balance', 'opening_balance', 'is_header'):
                if key in data and data[key] != getattr(self.instance, key):
                    self.add_error(key, 'Tidak dapat mengubah struktur/saldo awal akun yang telah mempunyai jurnal.')
        if data.get('is_header') and data.get('opening_balance'):
            self.add_error('opening_balance', 'Akun header tidak memiliki saldo.')
        return data


class PartyForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Party
        fields = ('code', 'name', 'kind', 'opening_balance', 'phone')
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()
    def clean(self):
        data = super().clean()
        if self.instance.pk and self.instance.journalline_set.exists():
            for key in ('code', 'kind', 'opening_balance'):
                if key in data and data[key] != getattr(self.instance, key):
                    self.add_error(key, 'Relasi yang memiliki transaksi tidak dapat diubah kode, jenis, atau saldo awalnya.')
        return data


class JournalEntryForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ('date', 'reference', 'description', 'kind')
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'description': forms.Textarea(attrs={'rows': 2})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get('date'):
            self.initial['date'] = timezone.localdate()
        self.fields['kind'].choices = [(k, n) for k, n in JournalEntry.Kind.choices if k != 'INVENTORY']
        self.style_fields()


class JournalLineForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = JournalLine
        fields = ('account', 'party', 'description', 'debit', 'credit')
        widgets = {'description': forms.TextInput(attrs={'placeholder': 'Opsional'}),
            'debit': forms.NumberInput(attrs={'step': '0.01', 'min': 0, 'placeholder': '0'}),
            'credit': forms.NumberInput(attrs={'step': '0.01', 'min': 0, 'placeholder': '0'})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(is_active=True, is_header=False)
        self.fields['party'].required = False
        self.fields['debit'].required = False
        self.fields['credit'].required = False
        self.style_fields()
    def clean(self):
        data = super().clean()
        if data.get('DELETE'):
            return data
        account, party = data.get('account'), data.get('party')
        d, c = data.get('debit') or Decimal('0'), data.get('credit') or Decimal('0')
        data['debit'], data['credit'] = d, c
        if account and (d > 0) == (c > 0):
            raise ValidationError('Isi debet ATAU kredit, bukan keduanya atau kosong.')
        if account and account.code == '1140' and (not party or party.kind != 'CUSTOMER'):
            self.add_error('party', 'Harus memilih pelanggan untuk akun 1140.')
        elif account and account.code == '2110' and (not party or party.kind != 'SUPPLIER'):
            self.add_error('party', 'Harus memilih pemasok untuk akun 2110.')
        elif account and account.code not in ('1140', '2110') and party:
            self.add_error('party', 'Akun selain 1140/2110 tidak memerlukan kode relasi.')
        return data


class BalancedJournalFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        rows = [f.cleaned_data for f in self.forms
                if f.cleaned_data and not f.cleaned_data.get('DELETE') and f.cleaned_data.get('account')]
        if len(rows) < 2:
            raise ValidationError('Minimal 2 baris akun untuk jurnal berpasangan.')
        debit = sum((r.get('debit') or Decimal('0') for r in rows), Decimal('0'))
        credit = sum((r.get('credit') or Decimal('0') for r in rows), Decimal('0'))
        if debit <= 0 or debit != credit:
            raise ValidationError(f'Jurnal tidak seimbang. Debet {debit:,.2f} dan kredit {credit:,.2f}.')


JournalLineFormSet = inlineformset_factory(
    JournalEntry, JournalLine, form=JournalLineForm, formset=BalancedJournalFormSet,
    extra=2, min_num=2, validate_min=True, can_delete=True, max_num=30, validate_max=True,
)


class ProductForm(StyledMixin, forms.ModelForm):
    opening_quantity = forms.DecimalField(label='Stok awal', required=False, initial=0,
        max_digits=18, decimal_places=3, min_value=Decimal('0'))
    opening_unit_cost = forms.DecimalField(label='Harga pokok awal per unit', required=False, initial=0,
        max_digits=20, decimal_places=2, min_value=Decimal('0'))
    opening_date = forms.DateField(label='Tanggal saldo awal', required=False,
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))

    class Meta:
        model = Product
        fields = ('code', 'name', 'unit', 'sale_price', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for key in ('opening_quantity', 'opening_unit_cost', 'opening_date'):
                self.fields.pop(key, None)
        else:
            self.fields['opening_date'].initial = timezone.localdate()
        self.style_fields()

    def clean(self):
        data = super().clean()
        if not self.instance.pk and (data.get('opening_quantity') or Decimal('0')) > 0:
            if not data.get('opening_date'):
                self.add_error('opening_date', 'Tanggal saldo awal wajib diisi.')
            if (data.get('opening_unit_cost') or Decimal('0')) <= 0:
                self.add_error('opening_unit_cost', 'Harga pokok awal wajib lebih dari nol.')
        return data


class MovementForm(StyledMixin, forms.Form):
    product = forms.ModelChoiceField(label='Barang', queryset=Product.objects.none())
    date = forms.DateField(label='Tanggal', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    reference = forms.CharField(label='Nomor bukti', max_length=50)
    kind = forms.ChoiceField(label='Jenis transaksi', choices=[('IN', 'Barang masuk / pembelian'), ('OUT', 'Barang keluar / penjualan')])
    quantity = forms.DecimalField(label='Jumlah unit', max_digits=18, decimal_places=3, min_value=Decimal('0.001'))
    unit_price = forms.DecimalField(label='Harga beli (masuk) / harga jual (keluar) per unit',
        max_digits=20, decimal_places=2, min_value=Decimal('0.01'))
    settlement_account = forms.ModelChoiceField(label='Akun pembayaran atau utang/piutang', queryset=Account.objects.none())
    party = forms.ModelChoiceField(label='Kode relasi (wajib jika memakai akun 1140/2110)',
                                  queryset=Party.objects.all(), required=False)
    description = forms.CharField(label='Keterangan', max_length=250)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        self.fields['settlement_account'].queryset = Account.objects.filter(is_active=True, is_header=False)
        self.fields['date'].initial = timezone.localdate()
        self.style_fields()


class ProfileForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = BusinessProfile
        fields = ('name', 'subtitle', 'address', 'phone', 'email', 'owner',
                  'inventory_account_code', 'cogs_account_code', 'sales_account_code')
        widgets = {'address': forms.Textarea(attrs={'rows': 3})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()
    def clean(self):
        data = super().clean()
        codes = [data.get('inventory_account_code'), data.get('cogs_account_code'),
                 data.get('sales_account_code')]
        if len(set(codes)) != 3:
            raise ValidationError('Kode akun Persediaan, HPP, dan Penjualan harus berbeda.')
        return data


class JournalPairForm(StyledMixin, forms.Form):
    """Satu baris input mewakili pasangan jurnal debet-kredit."""
    debit_account = forms.ModelChoiceField(label='Akun debet', queryset=Account.objects.none())
    credit_account = forms.ModelChoiceField(label='Akun kredit', queryset=Account.objects.none())
    amount = forms.DecimalField(label='Nominal transaksi (Rp)', max_digits=20, decimal_places=2,
                                min_value=Decimal('0.01'), widget=forms.NumberInput(attrs={
                                    'step': '0.01', 'min': '0.01', 'placeholder': 'Masukkan nominal'}))
    description = forms.CharField(label='Uraian', max_length=250, required=False,
                                  widget=forms.TextInput(attrs={'placeholder': 'Opsional'}))
    debit_party = forms.ModelChoiceField(label='Pelanggan (jika akun 1140)', queryset=Party.objects.none(), required=False)
    credit_party = forms.ModelChoiceField(label='Pemasok (jika akun 2110)', queryset=Party.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = Account.objects.filter(is_active=True, is_header=False)
        self.fields['debit_account'].queryset = accounts
        self.fields['credit_account'].queryset = accounts
        self.fields['debit_party'].queryset = Party.objects.filter(kind=Party.Kind.CUSTOMER)
        self.fields['credit_party'].queryset = Party.objects.filter(kind=Party.Kind.SUPPLIER)
        self.style_fields()

    def clean(self):
        data = super().clean()
        debit_account, credit_account = data.get('debit_account'), data.get('credit_account')
        debit_party, credit_party = data.get('debit_party'), data.get('credit_party')
        if debit_account and debit_account.code == '1140' and not debit_party:
            self.add_error('debit_party', 'Pilih pelanggan untuk akun 1140.')
        elif debit_account and debit_account.code != '1140' and debit_party:
            self.add_error('debit_party', 'Relasi pelanggan hanya untuk akun 1140.')
        if credit_account and credit_account.code == '2110' and not credit_party:
            self.add_error('credit_party', 'Pilih pemasok untuk akun 2110.')
        elif credit_account and credit_account.code != '2110' and credit_party:
            self.add_error('credit_party', 'Relasi pemasok hanya untuk akun 2110.')
        return data


from django.forms import formset_factory
JournalPairFormSet = formset_factory(
    JournalPairForm, extra=1, min_num=1, validate_min=True,
    can_delete=True, max_num=15, validate_max=True,
)


class AutoJournalForm(StyledMixin, forms.ModelForm):
    """Form jurnal umum: admin hanya mengisi keterangan dan satu nominal.

    Termin dan diskon bersifat opsional; akun debet/kredit tetap ditentukan otomatis.
    """
    amount = forms.DecimalField(
        label='Nominal transaksi (Rp)', max_digits=20, decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'step': '0.01', 'min': '0.01', 'placeholder': 'Masukkan nominal transaksi'
        })
    )
    term_text = forms.CharField(
        label='Termin pembayaran', required=False, max_length=30,
        widget=forms.TextInput(attrs={'list': 'termSuggestions', 'placeholder': 'Contoh: 2/10,n/30',
                                      'autocomplete': 'off'}),
        help_text='n/30 = jatuh tempo 30 hari. 2/10,n/30 = diskon 2% bila lunas ≤10 hari, jatuh tempo 30 hari.')
    discount_percent = forms.DecimalField(
        label='Diskon (%)', required=False, min_value=Decimal('0'), max_value=Decimal('99.99'),
        max_digits=5, decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': '0'}))
    discount_rp = forms.DecimalField(
        label='Diskon (Rp)', required=False, min_value=Decimal('0'), max_digits=20, decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': '0'}))
    use_term_discount = forms.BooleanField(
        label='Lunas dalam masa diskon termin (pakai potongan dari termin)', required=False)

    class Meta:
        model = JournalEntry
        fields = ('date', 'description')
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Contoh: Pembelian pupuk tunai / Penjualan hasil tani kredit'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get('date'):
            self.initial['date'] = timezone.localdate()
        self.fields['amount'].required = True
        self.style_fields()

    def clean(self):
        data = super().clean()
        if data.get('discount_percent') and data.get('discount_rp'):
            self.add_error('discount_rp', 'Isi diskon dalam persen ATAU rupiah, tidak keduanya.')
        return data
