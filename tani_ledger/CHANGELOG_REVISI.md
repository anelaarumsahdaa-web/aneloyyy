# Perubahan AgriBooks - Jurnal Penyesuaian + Excel Dinamis

## Revisi 2026-11-11 (jurnal umum otomatis lanjutan)

- **Hapus jurnal** (salah input): tombol Hapus di daftar dan detail jurnal, dengan halaman konfirmasi.
  Jurnal dari Transaksi Stok ikut membatalkan mutasi dan lapisan FIFO, tetapi hanya bila mutasi itu
  yang paling akhir untuk barangnya (kalau tidak, sistem menolak dan menjelaskan alasannya).
- **Pratinjau otomatis** di form Jurnal Umum: saat keterangan diketik, akun debet/kredit langsung terisi;
  setelah nominal dimasukkan sekali, kolom debet dan kredit ikut terisi.
- **Termin & diskon** (opsional): termin `n/30` atau `2/10,n/30` (jatuh tempo tersimpan), diskon % atau Rp,
  dan "potongan termin" saat penerimaan piutang / pembayaran utang. Diskon dicatat ke akun Potongan.
- **Retur**: keterangan "retur penjualan ..." dan "retur pembelian ..." dikenali.
- **Akun baru** (jalankan `python manage.py seed_agriculture` pada database lama):
  4130 Retur Penjualan, 4140 Potongan Penjualan, 5120 Retur Pembelian, 5130 Potongan Pembelian.
- **Produk baru**: `python manage.py seed_produk_tani` menambah Bibit Tanaman (2.000 bibit, total Rp500.000),
  Pupuk Kompos (100 kg × Rp10.000), Penyemprot Hama (15 pcs × Rp150.000) beserta saldo awal akun 1150 dan 3100.
- Nama produk terdaftar (mis. "pupuk kompos") pada keterangan pembelian dicatat sebagai Persediaan 1150.
- Perbaikan: nomor bukti jurnal umum tidak lagi bisa bentrok setelah ada jurnal yang dihapus;
  tanggal default form jurnal kini terisi hari ini; tes lama yang kedaluwarsa diperbarui (26 tes lulus).
- Migrasi baru: `0002_termin_diskon_jurnal` (jalankan `python manage.py migrate`).

## Revisi 2026-11-09

### 1. Jurnal penyesuaian sesudah Buku Besar

- Sidebar sekarang berurutan: Buku Besar -> Jurnal Penyesuaian -> Buku Besar Pembantu.
- Alamat `http://127.0.0.1:8000/adjustments/` untuk daftar jurnal penyesuaian.
- Alamat `http://127.0.0.1:8000/adjustments/new/` untuk membuat jurnal penyesuaian.
- Form memaksa jenis `ADJUSTMENT` dari server. Jurnal Umum memaksa `GENERAL`.
- Jurnal penyesuaian ditampilkan terpisah dari jurnal umum, tetapi tetap masuk buku besar dan laporan.

### 2. Daftar Akun dan Kode tersembunyi dari navigasi

- Tidak tampil di sidebar.
- Master data tetap tersedia, tidak dihapus dari database.
- Saat ekspor, AKUN dan KODE selalu disertakan.
- Untuk menambah/mengubah manual, URL lama `/accounts/` dan `/parties/` tetap aktif.

### 3. Export Excel dengan formula

- Semua tombol ekspor menghasilkan satu workbook terhubung berisi 12 sheet.
- Sheet dipilih menjadi tab aktif bila pengguna ekspor dari satu halaman tertentu.
- Kolom debet/kredit pada jurnal umum dan penyesuaian menjadi input.
- Buku Besar dan Buku Besar Pembantu memiliki saldo berjalan berbasis rumus.
- Neraca Saldo, Neraca Lajur, Laba Rugi, Neraca bergantung pada rumus antarsheet.
- Input kuantitas dan harga pembelian/penjualan pada INVENTORY CARD menggerakkan
  perhitungan FIFO per lot melalui kolom pembantu tersembunyi (U dan seterusnya).
- Jurnal yang dibuat otomatis dari transaksi persediaan merujuk pada perhitungan
  INVENTORY CARD. Ganti harga beli -> HPP dan laporan turut berubah.
- Nilai sel nol tampil "-" dan angka negatif merah bertanda kurung.
- Workbook disetel untuk perhitungan ulang otomatis ketika dibuka Excel.

**Batasan penting**: perubahan pada file Excel tidak kembali ke database Django.
Perubahan nominal, kuantitas, dan harga pada baris yang sudah diekspor dihitung ulang.
Penambahan, penghapusan, perubahan kode akun, atau perubahan urutan tanggal
membutuhkan ekspor baru agar struktur transaksi dan FIFO cocok.

## Upgrade dari ZIP lama

1. Cadangkan folder website lama, terutama `db.sqlite3` dan file `.env` kalau ada.
2. Ekstrak ZIP versi ini ke folder baru. Jangan menimpa database tanpa cadangan.
3. Jika ingin melanjutkan data lama, salin `db.sqlite3` dan `.env` dari proyek lama
   ke folder proyek baru yang sama levelnya dengan `manage.py`.
4. Aktifkan lingkungan Python lama atau buat ulang virtualenv, lalu jalankan:

```powershell
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test accounting
python manage.py runserver
```

Tidak ada penambahan tabel/model baru, jadi migrasi skema baru tidak diperlukan.
Untuk instalasi dari nol, ikuti README.md.

## Pengujian

- Sintaks seluruh file Python diuji menggunakan `compileall`.
- Logika builder workbook diuji melalui *mocked smoke test* untuk transaksi
  umum, jurnal penyesuaian, saldo awal, transaksi stok, dan database kosong.
- Rumus FIFO skalar diuji dengan mesin spreadsheet pada contoh 100 kg x 20.000,
  pembelian 30 kg x 22.000, penjualan 110 kg: HPP 2.220.000.
  Saat stok awal diubah 90 kg: HPP berubah menjadi 2.240.000.
- **Belum menjalankan Django test suite sebenarnya** di lingkungan pembuatan
  karena Django dan openpyxl belum tersedia dan instalasi paket terhalang jaringan.
  Jalankan `python manage.py test accounting` setelah instalasi di komputer pengguna.

## Revisi 2026-11-11 - Input Jurnal Berpasangan

- Form Jurnal Umum dan Jurnal Penyesuaian sekarang memakai input akun debet, akun kredit, dan satu nominal.
- Setiap pasangan otomatis disimpan sebagai dua `JournalLine`: satu sisi debet dan satu sisi kredit dengan nominal sama.
- Relasi pelanggan tetap wajib untuk akun 1140; relasi pemasok tetap wajib untuk akun 2110.
- Tidak ada perubahan model/database dan tidak memerlukan migrasi baru.


## Revisi lanjutan: Jurnal Umum otomatis dari keterangan + satu nominal

- Form Jurnal Umum sekarang hanya meminta tanggal, keterangan transaksi, dan satu nominal. Nomor bukti dibuat otomatis dengan pola `JU-YYYYMMDD-###`.
- Akun debet/kredit ditentukan di sisi server berdasarkan kata kunci transaksi.
- Sistem membuat dua baris jurnal dengan nominal yang sama: satu di debet dan satu di kredit.
- Jurnal Penyesuaian tetap memakai form pasangan akun manual dan tidak ikut diubah.
- Transaksi yang belum dikenali atau cara pembayarannya belum jelas ditolak dengan pesan agar keterangan diperjelas; sistem tidak menebak akun.
- Untuk transaksi piutang/utang, nama atau kode pelanggan/pemasok perlu ada di keterangan jika terdapat lebih dari satu relasi sejenis. Jika hanya ada satu relasi, sistem menggunakannya otomatis.

Contoh keterangan yang didukung: `Pembelian pupuk tunai`, `Pembelian pupuk kredit [nama pemasok]`, `Penjualan hasil tani tunai`, `Penjualan hasil tani kredit [nama pelanggan]`, `Pembayaran listrik tunai`, `Pembayaran upah tunai`, `Penerimaan piutang [nama pelanggan]`, dan `Pembayaran utang [nama pemasok]`. Untuk pembayaran melalui bank, tambahkan kata `transfer` atau `bank`.
