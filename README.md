# PikApp - ScheduleApp

PikApp adalah aplikasi penjadwalan pengangkutan sampah untuk BSU (Bank Sampah Unit). Proyek ini terdiri dari backend FastAPI dan aplikasi Android Kotlin/Jetpack Compose. Backend mengelola autentikasi Firebase, data BSU, pengajuan perubahan jadwal, riwayat pengangkutan, serta generate jadwal otomatis menggunakan Genetic Algorithm. Aplikasi Android menyediakan tampilan untuk admin dan user BSU.

## Daftar Isi

- [Fitur Utama](#fitur-utama)
- [Teknologi](#teknologi)
- [Struktur Proyek](#struktur-proyek)
- [Prasyarat](#prasyarat)
- [Konfigurasi Firebase dan Google Maps](#konfigurasi-firebase-dan-google-maps)
- [Menjalankan Backend](#menjalankan-backend)
- [Menjalankan Aplikasi Android](#menjalankan-aplikasi-android)
- [Endpoint API Utama](#endpoint-api-utama)
- [Alur Penjadwalan](#alur-penjadwalan)
- [Catatan Pengujian](#catatan-pengujian)
- [Catatan Keamanan](#catatan-keamanan)

## Fitur Utama

### User BSU

- Login menggunakan Firebase Authentication.
- Melihat profil BSU.
- Mengubah data profil, termasuk alamat, kecamatan, nomor telepon, dan koordinat lokasi.
- Melihat jadwal pengangkutan yang sudah dipublikasikan.
- Melihat jadwal milik BSU sendiri.
- Mengajukan perubahan jadwal, seperti reschedule atau pembatalan.
- Melihat riwayat pengangkutan sampah.
- Melihat kalender dan hari libur Indonesia.

### Admin

- Verifikasi akses admin berdasarkan role pengguna.
- Mendaftarkan BSU baru dan membuat akun Firebase untuk BSU tersebut.
- Melihat daftar BSU aktif dan nonaktif.
- Mengelola pengajuan perubahan jadwal dari user.
- Generate jadwal pengangkutan otomatis.
- Mengedit draft jadwal sebelum dipublikasikan.
- Mempublikasikan jadwal agar bisa dilihat user.
- Finalisasi jadwal setelah siap digunakan sebagai jadwal operasional.
- Menghapus slot jadwal tertentu atau seluruh jadwal bulanan.
- Melihat dan memperbarui riwayat operasional pengangkutan.

## Teknologi

### Backend

- Python 3.11
- FastAPI
- Uvicorn
- Firebase Admin SDK
- Firestore
- Pandas dan OpenPyXL
- Library `holidays` untuk kalender hari libur Indonesia
- Docker dan Docker Compose

### Frontend Android

- Kotlin
- Jetpack Compose
- Material 3
- Firebase Authentication
- Firebase Firestore
- Retrofit
- Google Maps dan Places API
- Lottie
- Kizitonwose Calendar Compose

## Struktur Proyek

```text
.
|-- backend/
|   |-- Dockerfile
|   |-- requirements.txt
|   `-- app/
|       |-- main.py
|       |-- database.py
|       |-- dependencies.py
|       |-- routers/
|       |-- models/
|       |-- services/
|       |-- utils/
|       |-- dummy/
|       `-- scripts/
|-- frontend/
|   `-- ScheduleApp/
|       |-- build.gradle.kts
|       |-- settings.gradle.kts
|       |-- gradle/
|       `-- app/
|           |-- build.gradle.kts
|           `-- src/
|-- compose.yaml
`-- README.md
```

## Prasyarat

Pastikan perangkat sudah memiliki:

- Python 3.11 atau lebih baru.
- Docker dan Docker Compose jika ingin menjalankan backend melalui container.
- Android Studio.
- JDK 11.
- Akun Firebase dengan Authentication dan Firestore aktif.
- Google Maps API key untuk fitur lokasi Android.

## Konfigurasi Firebase dan Google Maps

### Backend

Backend membaca credential Firebase dari file:

```text
backend/app/serviceAccountKey.json
```

File tersebut harus berasal dari Firebase Admin SDK service account. Karena berisi credential sensitif, file ini sebaiknya tidak dimasukkan ke repository publik.

### Android

Aplikasi Android menggunakan file Firebase:

```text
frontend/ScheduleApp/app/google-services.json
```

Untuk Google Maps, siapkan API key dan pastikan konfigurasi `MAPS_API_KEY` tersedia untuk Secrets Gradle Plugin. Android manifest membaca key tersebut melalui:

```xml
${MAPS_API_KEY}
```

## Menjalankan Backend

### Opsi 1 - Docker Compose

Dari root proyek:

```bash
docker compose up --build
```

Backend akan berjalan pada:

```text
http://localhost:8000
```

Endpoint pengecekan awal:

```text
GET http://localhost:8000/
```

### Opsi 2 - Lokal tanpa Docker

Masuk ke folder backend:

```bash
cd backend
python -m venv .venv
```

Aktifkan virtual environment.

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependency:

```bash
pip install -r requirements.txt
```

Jalankan API dari folder `backend/app`:

```bash
cd app
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Menjalankan Aplikasi Android

1. Buka folder berikut di Android Studio:

```text
frontend/ScheduleApp
```

2. Sync Gradle project.
3. Pastikan `google-services.json` tersedia di folder `app`.
4. Pastikan `MAPS_API_KEY` sudah dikonfigurasi.
5. Jalankan aplikasi melalui emulator atau perangkat Android.

### Konfigurasi Base URL API

Base URL API berada di:

```text
frontend/ScheduleApp/app/src/main/java/com/example/scheduleapp/data/api/ApiConfig.kt
```

Saat ini aplikasi mengarah ke:

```kotlin
private const val BASE_URL = "https://pikapp.ghavio.my.id"
```

Jika ingin memakai backend lokal dari emulator Android, gunakan alamat seperti:

```kotlin
private const val BASE_URL = "http://10.0.2.2:8000/"
```

Jika memakai perangkat fisik, gunakan alamat IP komputer yang menjalankan backend, misalnya:

```kotlin
private const val BASE_URL = "http://192.168.100.10:8000/"
```

## Endpoint API Utama

Sebagian besar endpoint membutuhkan header:

```text
Authorization: Bearer <firebase_id_token>
```

### Umum

| Method | Endpoint | Fungsi |
| --- | --- | --- |
| GET | `/` | Mengecek API dan metadata aplikasi |
| GET | `/user` | Mengambil profil user berdasarkan Firebase token |

### User

| Method | Endpoint | Fungsi |
| --- | --- | --- |
| GET | `/bsu-detail` | Mengambil detail BSU milik user |
| PUT | `/bsu/update` | Mengubah profil BSU |
| GET | `/periode/{tahun}/{bulan}/active` | Mengecek status periode |
| POST | `/schedule-request` | Mengirim pengajuan jadwal |
| GET | `/schedule?tahun=&bulan=` | Mengambil jadwal yang sudah publish/finalized |
| GET | `/my-schedule?tahun=&bulan=` | Mengambil jadwal milik user |
| GET | `/history` | Mengambil riwayat pengangkutan user |
| DELETE | `/schedule-request/{request_id}` | Menghapus pengajuan user |
| GET | `/holidays?tahun=&bulan=` | Mengambil hari libur Indonesia |

### Admin

| Method | Endpoint | Fungsi |
| --- | --- | --- |
| GET | `/verify-admin` | Mengecek akses admin |
| POST | `/admin/create-bsu` | Mendaftarkan BSU baru |
| GET | `/bsu-list` | Mengambil seluruh data BSU |
| GET | `/admin/schedule-requests` | Mengambil daftar pengajuan jadwal |
| PUT | `/admin/schedule-requests/{request_id}/approve` | Menyetujui pengajuan |
| PUT | `/admin/schedule-requests/{request_id}/reject` | Menolak pengajuan |
| GET | `/admin/history` | Mengambil riwayat operasional |
| PUT | `/admin/history/status` | Mengubah status riwayat operasional |
| POST | `/generate-schedule` | Membuat draft jadwal otomatis |
| GET | `/schedule/{tahun}/{bulan}` | Mengambil jadwal untuk admin |
| PUT | `/schedule/{tahun}/{bulan}/update-draft` | Mengubah draft jadwal |
| PUT | `/schedule/{tahun}/{bulan}/publish` | Mempublikasikan jadwal |
| PUT | `/schedule/{tahun}/{bulan}/finalize` | Finalisasi jadwal |
| DELETE | `/schedule/{tahun}/{bulan}/slot` | Menghapus satu slot BSU pada tanggal tertentu |
| DELETE | `/schedule/{tahun}/{bulan}` | Menghapus jadwal bulanan |

## Alur Penjadwalan

1. Admin memastikan data BSU aktif sudah lengkap, termasuk nama, kecamatan, estimasi volume, dan koordinat.
2. Admin memilih tahun, bulan, kapasitas kendaraan, dan kuota kunjungan per hari.
3. Backend mengambil daftar BSU aktif dari Firestore.
4. Backend mengambil volume historis terakhir dari jadwal dan riwayat pickup sebelumnya.
5. Sistem menentukan hari kerja pada bulan target, dengan mengecualikan akhir pekan dan hari libur Indonesia.
6. Genetic Algorithm membuat draft jadwal berdasarkan constraint berikut:
   - seluruh BSU aktif dijadwalkan;
   - minimal satu BSU pada hari kerja jika data memungkinkan;
   - jumlah BSU per hari tidak melebihi kuota kunjungan;
   - total volume harian tidak melebihi kapasitas kendaraan;
   - BSU dengan kecamatan yang sama diprioritaskan berada dalam hari yang sama.
7. Draft jadwal disimpan ke collection `jadwal` dengan status `draft`.
8. Admin dapat meninjau dan mengubah draft.
9. Admin mempublikasikan jadwal dengan status `published`.
10. User dapat melihat jadwal dan mengajukan perubahan jika dibutuhkan.
11. Admin dapat menyetujui atau menolak pengajuan.
12. Jadwal dapat difinalisasi menjadi status `finalized`.

## Koleksi Firestore

Koleksi utama yang digunakan aplikasi:

| Collection | Fungsi |
| --- | --- |
| `users` | Data user, email, UID, dan role |
| `bsu` | Profil BSU dan status keaktifan |
| `jadwal` | Jadwal bulanan, status jadwal, dan detail hasil GA |
| `schedule_requests` | Pengajuan reschedule atau pembatalan dari user |
| `pickup_history` | Riwayat operasional pengangkutan |

## Catatan Pengujian

Backend memiliki beberapa script untuk data dummy dan pengujian generate jadwal di:

```text
backend/app/dummy/
backend/app/test_ga.py
```

Aplikasi Android memiliki folder test standar di:

```text
frontend/ScheduleApp/app/src/test/
frontend/ScheduleApp/app/src/androidTest/
```

Untuk menjalankan unit test Android:

```bash
cd frontend/ScheduleApp
./gradlew test
```

Di Windows:

```powershell
cd frontend\ScheduleApp
.\gradlew.bat test
```

## Ringkasan

PikApp membantu pengelolaan jadwal pengangkutan sampah BSU secara digital. Admin dapat mengelola BSU, membuat jadwal otomatis dengan Genetic Algorithm, mempublikasikan jadwal, dan memantau riwayat operasional. User BSU dapat melihat jadwal, mengubah profil, dan mengajukan perubahan jadwal melalui aplikasi Android.
