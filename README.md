# MHFU Patcher

Ubah **IPA asli** Monster Hunter Freedom Unite (iOS 1.00.11) menjadi build
yang **sama persis** dengan build patch 1.00.194 yang sudah diuji di device:
safe area/HUD, analog, teks & latar loading, posisi peta, bingkai coating
sejajar bar, dan dukungan controller MFi.

Semua proses berjalan di komputer sendiri. IPA diunggah ke server lokal
(`127.0.0.1`), bukan ke internet.

## Isi patch

| fitur | contoh perubahan |
|---|---|
| Skala UI & konstanta render | 8 rentang byte |
| Safe area, HUD kanan, tombol submit | 15 rentang byte |
| Rect & radius analog | 4 rentang byte |
| Teks/latar loading & peta | 5 rentang byte |
| Bingkai coating sejajar bar (A/B) | 4 rentang byte |

Total **36 rentang / 1.008 byte** pada slice `arm64`, plus penyesuaian paket:

- biner dijadikan **thin arm64** (ukuran 8.593.744 B) — identik dengan build teruji
- `Info.plist`: versi baru, `UIDeviceFamily = [1]`, `UILaunchStoryboardName`,
  2 kunci izin Bluetooth (controller MFi)
- 11 member lama dibuang (`LaunchImage*`, `_CodeSignature/*`, `iTunesArtwork`,
  `iTunesMetadata.plist`, `.ZipComment`)
- 1 member ditambah (`LaunchScreen.storyboard`)
- 14.201 member lain disalin apa adanya

## Syarat

- Python 3.10+ dan FastAPI + uvicorn (dipasang otomatis ke `.venv` oleh
  `./run.sh`; lihat `requirements.txt`)
- Node.js hanya bila mau membangun ulang UI
- Ruang disk ± 1,7 GB saat memproses (input + output)
- IPA sumber: hasil dekripsi (bukan dari App Store langsung)

Perintah `inspect` dan `patch` di CLI cukup memakai Python stdlib; FastAPI
hanya dibutuhkan untuk `serve`.

## Pakai lewat browser

```bash
./run.sh
```

UI satu kartu (React + shadcn/ui, hitam-putih, teks bahasa Inggris):

1. klik **Choose IPA**, pilih IPA asli dari dialog file
2. klik **Patch**
3. setelah selesai muncul **Patch complete** dan tombol **Download IPA**

Tidak ada input path. Berkas diunggah ke server lokal (loopback), dipatch,
lalu disediakan sebagai unduhan. Progress menampilkan fase unggah dan patch.

Berkas kerja disimpan sementara di `~/.cache/fupatch` (bisa diubah lewat
`FUPATCH_WORKSPACE` atau `--workdir`). Server menyimpan dua hasil terakhir;
unduh hasil sebelum memproses IPA lain. IPA sumber tidak pernah diubah.

## Pakai lewat CLI

```bash
# periksa saja
python3 -m mhfu_patch inspect --ipa MHFU_asli.ipa

# patch
python3 -m mhfu_patch patch --ipa MHFU_asli.ipa \
    --out MHFU_patched_1.00.194.ipa --version 1.00.194

# uji tanpa menulis file
python3 -m mhfu_patch patch --ipa MHFU_asli.ipa --out /tmp/x.ipa --dry-run

# server saja (tanpa membuka browser; butuh venv/FastAPI)
.venv/bin/python -m mhfu_patch serve --port 8765
```

Opsi `patch`: `--keep-fat` (pertahankan biner FAT), `--force` (timpa output),
`--patch-set ID`.

Kode keluar: `0` sukses · `2` input tidak didukung · `3` byte biner tidak cocok ·
`4` ruang disk kurang.

## Pemasangan ke device

IPA hasil belum ditandatangani. Pasang lewat **AltStore**, **Sideloadly**, atau
alat serupa — installer akan menandatangani ulang dengan Apple ID kamu.
Versi yang tampil di Settings harus sama dengan versi yang diisi di patcher.

## Verifikasi

Patcher memverifikasi dirinya sendiri:

1. sha256 slice setelah langkah biner **wajib** sama dengan
   `25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`
2. setelah IPA ditulis, biner diekstrak ulang dari hasil dan sha-nya dicek lagi
3. versi di `Info.plist` hasil dicek ulang

Kalau ada yang tidak cocok, file `.part` dihapus dan tidak ada output tertinggal.

Cek mandiri:

```bash
python3 -m mhfu_patch inspect --ipa hasil.ipa --json
```

## Kalau gagal

| pesan | arti |
|---|---|
| `IPA is still encrypted` | IPA dari App Store; butuh hasil dekripsi |
| `unknown binary` | bukan IPA MHFU 1.00.11 yang didukung (atau sudah dimodifikasi lain) |
| `step … does not match` | byte biner berbeda dari yang diharapkan; kirim pesan lengkapnya |
| `ZIP64 archives are not supported` | IPA dikemas dengan ZIP64; ekstrak & zip ulang tanpa ZIP64 |
| `not enough disk space` | sisakan ± 1,7 GB di folder tujuan |
| `not a readable IPA` | berkas yang diunggah bukan arsip IPA yang valid |

### Membangun ulang UI

Sumber UI ada di `ui/` (Vite + React + TypeScript + Tailwind + komponen
shadcn/ui). Hasil build disimpan di `mhfu_patch/web`, jadi pengguna tidak
perlu Node.js.

```bash
cd ui && npm install && npm run build
```

Menambah komponen shadcn lain:

```bash
cd ui && npx shadcn@latest add dialog
```

## Pengembangan

```bash
# sekali saja: dependency server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# tes cepat (tanpa file besar)
.venv/bin/python -m unittest discover -s tests -v

# tes end-to-end penuh (butuh IPA asli + golden build)
MHFU_E2E=1 .venv/bin/python -m unittest tests.test_cli_e2e -v

# buat ulang manifest dari pasangan biner
python3 tools/make_manifest.py \
  --original-ipa "IPA asli.ipa" \
  --final-bin ../re_mhfu/mh_unite_c194 \
  --intermediate-bin ../re_mhfu/mh_unite_base186 \
  --patched-ipa ../MHFU_load194.ipa \
  --out patches/mhfu-1.00.194.json
```

Struktur:

```
ui/              sumber UI (Vite + React + shadcn/ui)
mhfu_patch/
  web/           hasil build UI (HTML/JS/CSS) yang disajikan server
  macho.py       fat/thin, slice arm64, cryptid
  manifest.py    muat + validasi patch set, cocokkan sha
  engine.py      inspeksi, langkah biner, tulis + verifikasi
  package.py     hapus/tambah member, Info.plist
  ziprewrite.py  tulis ulang IPA (streaming, atomik)
  jobs.py        job latar + event SSE
  server.py      FastAPI 127.0.0.1: unggah, patch, SSE, unduh
patches/         manifest patch (satu file per build)
assets/          fixture LaunchScreen.storyboard
tools/           pembuat manifest (dev)
tests/           unit + e2e
requirements.txt dependensi server (FastAPI + uvicorn)
run.sh           penyiap .venv + pembuka UI
```

Menambah build patch baru: jalankan `tools/make_manifest.py` dengan pasangan
biner baru; `patches/index.json` memilih patch set otomatis berdasarkan sha
slice IPA masukan.

## Batasan

- Hanya untuk IPA 1.00.11 yang dekripsiannya cocok dengan sha di manifest.
- Patch bersifat all-or-nothing (36 langkah sekaligus); toggle per fitur belum
  tersedia karena beberapa cave dipakai bersama antar fitur.
- Biner hasil default thin arm64; `--keep-fat` mempertahankan slice armv7 asli
  (tidak dipatch).
