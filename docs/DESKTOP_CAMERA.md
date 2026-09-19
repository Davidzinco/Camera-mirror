# Kamera laptop melalui Wi-Fi — prototipe Tahap A

Target pertama pengguna: **laptop Windows 11 sebagai pengirim → desktop Linux
sebagai penerima**. Kedua perangkat belum tersedia untuk pengujian bersama.
Kode juga menyediakan arah sebaliknya, tetapi dukungan lintas OS belum dinyatakan
tervalidasi sampai matriks pengujian fisik selesai.

## Yang tersedia

- Pemilih kamera melalui Qt Multimedia, capture hingga 720p dengan target kirim
  30 fps, dan preview pengirim/penerima.
- Satu pengirim dan satu penerima lewat WebRTC pada LAN, tanpa server cloud/STUN/TURN.
- Undangan manual berisi IP, port, fingerprint sertifikat, dan token acak. HTTPS
  diverifikasi terhadap fingerprint sebelum token dikirim; media memakai WebRTC.
- Undangan berlaku lima menit, satu kali untuk membuka sesi, dengan batas lima
  percobaan salah. Kredensial sesi juga mengautentikasi permintaan berhenti.
- Output kamera virtual melalui pyvirtualcam: v4l2loopback di Linux, OBS di Windows.
- Tema gelap/terang yang disimpan, bantuan koneksi, stop, dan penghentian saat
  jendela ditutup. Antrean antarbagian hanya menyimpan frame terbaru.

Belum tersedia: discovery mDNS komputer, perangkat tepercaya persisten,
reconnect otomatis, audio, relay HP -> laptop -> desktop, installer binary mandiri (.exe/AppImage),
dan pemilihan bitrate/codec. Mode Android yang sudah ada tetap tersedia terpisah
melalui `camera_mirror.py` pada Linux. Menutup jendela Android masih mengikuti
perilaku lama: layanan kamera tetap berjalan sampai dihentikan.

## Instalasi aplikasi

Cara termudah: unduh/ekstrak ZIP `main`, lalu jalankan **Install-Windows.cmd** atau
**Install-Linux.sh**. Installer menyiapkan lingkungan Python dan pintasan pengguna.
Lihat [langkah beberapa klik di README](../README.md#instalasi-mudah--mulai-di-sini).
Bagian di bawah adalah alternatif manual. Driver kamera virtual tetap disiapkan
terpisah pada komputer penerima.

Jalankan perintah dari root repositori pada kedua komputer. Python **3.12 64-bit**
adalah target job CI desktop; pengujian lokal pengembangan menggunakan Linux
Python 3.14.7. Matriks ini belum menentukan semua versi OS/Python yang didukung.

Windows 11 (PowerShell):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe desktop_camera.py
```

Linux:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-desktop.txt
.venv/bin/python desktop_camera.py
```

PySide6 membutuhkan lingkungan desktop dan library platform Qt yang sesuai.
Apabila plugin `xcb`/Wayland gagal dimuat, periksa dependensi Qt pada distro;
mode `QT_QPA_PLATFORM=offscreen` hanya untuk tes otomatis, bukan penggunaan harian.

Alternatif entry point: `python camera_mirror.py --desktop` memakai interpreter
yang sedang aktif. Pada Windows, `camera_mirror.py` langsung membuka UI desktop
sebelum mengimpor backend Linux. Pada UI Android Linux, tombol **Kamera komputer**
memakai `.venv/bin/python` bila tersedia.

`requirements.txt` tetap untuk fitur Android lama. Jika tombol **Buka kamera HP
Android** dipakai dari lingkungan desktop, pasang juga `requirements.txt`, Tkinter,
dan dependensi Android/Linux pada README. UI Android kini menggunakan warna gelap.

## Siapkan kamera virtual pada penerima

Pengirim Windows yang hanya membagikan kamera fisik **tidak membutuhkan OBS**.
Driver/backend virtual dibutuhkan di komputer penerima.

### Desktop Linux

Pasang v4l2loopback dan header yang cocok dengan kernel aktif melalui pengelola
paket distro. Pada CachyOS/Arch, paket yang digunakan proyek adalah
`v4l2loopback-dkms` dan `v4l2loopback-utils`.

Untuk modul yang **belum dimuat**, contoh membuat satu perangkat khusus:

```bash
sudo modprobe v4l2loopback devices=1 video_nr=20 card_label="Camera Mirror" exclusive_caps=1
```

Pastikan `/dev/video20` belum digunakan perangkat lain. Jika modul sudah dimuat,
`modprobe` tidak mengganti konfigurasi perangkat yang ada. Gunakan perangkat
loopback yang tersedia, atau tambahkan perangkat kosong dengan utilitas yang
mendukung pembuatan dinamis:

```bash
sudo v4l2loopback-ctl add -n "Camera Mirror" -x 1 /dev/video20
```

Pilih `/dev/video20` pada **Pengaturan lanjutan → Perangkat virtual** di penerima.
Periksa izin akses perangkat untuk pengguna desktop. Jangan menjalankan seluruh
GUI sebagai root. Perangkat Android `/dev/video10` juga bisa dipakai bila sudah
siap dan tidak sedang digunakan stream Android, tetapi labelnya tetap Android Webcam.
Jangan memakai perangkat yang sedang ditulis aplikasi lain.

Perangkat virtual dapat baru muncul sebagai kamera di aplikasi lain setelah
penerima mulai mengirim frame ke perangkat. Buka ulang pemilih kamera jika perlu.
Detail modul: [dokumentasi v4l2loopback](https://github.com/v4l2loopback/v4l2loopback).

### Windows sebagai penerima (pengujian tambahan)

Pasang OBS Studio beserta komponen Virtual Camera. Biarkan isian perangkat virtual
kosong untuk backend OBS. Jangan menjalankan **Start Virtual Camera** di OBS
bersamaan dengan Camera Mirror karena backend tersebut dipakai sebagai keluaran
oleh aplikasi ini. Pilih **OBS Virtual Camera** pada aplikasi tujuan.
Lihat [kebutuhan backend pyvirtualcam](https://github.com/letmaik/pyvirtualcam).

## Alur Windows 11 → Linux

1. Hubungkan kedua komputer ke LAN yang sama. Salah satu boleh memakai Ethernet.
2. Laptop Windows: buka aplikasi, pilih **Kirim**, kamera bawaan/USB, dan IP Wi-Fi
   laptop. Jika ada VPN/adaptor lain, pilih alamat yang dapat dijangkau desktop.
3. Klik **Mulai bagikan kamera**. Kamera aktif dan undangan ditampilkan.
4. Klik **Salin undangan**. Pindahkan seluruh teks `cm1:...` melalui kanal pribadi
   ke desktop yang akan menerima. Undangan adalah kredensial akses kamera sesi itu.
5. Desktop Linux: pilih **Terima**, tempel undangan, tentukan `/dev/video20` jika
   diperlukan, kemudian klik **Hubungkan kamera**.
6. Pastikan status menyebut **kamera virtual aktif**, lalu pilih **Camera Mirror**
   atau nama perangkat yang ditampilkan di OBS dan aplikasi panggilan/browser.
7. Klik **Berhenti** atau tutup jendela desktop. Penghentian diberitahukan ke laptop
   jika jaringan masih tersedia. Setelah terputus, mulai lagi dengan undangan baru.

Kamera berjalan hanya setelah aksi mulai. Undangan dihapus dari UI setelah dipakai
atau sesi berhenti. Jika clipboard masih berisi undangan yang disalin aplikasi,
clipboard dibersihkan saat undangan dihapus. Kamera tidak otomatis dibagikan ke
perangkat baru setelah koneksi putus.

## Troubleshooting

| Kondisi | Tindakan |
| --- | --- |
| Kamera tidak ditemukan | Klik Cari ulang, periksa izin kamera Windows, sambungan USB, dan aplikasi lain yang memakai kamera. |
| Tidak bisa menghubungkan | Pastikan IP pengirim benar; izinkan TCP port pengirim (default 8765) dan trafik UDP aplikasi pada firewall LAN pribadi. |
| Satu Wi-Fi tetapi tetap gagal | Periksa client isolation/jaringan tamu. Tidak ada dukungan relay internet pada prototipe. |
| Undangan ditolak | Mulai ulang di pengirim dan salin undangan baru; undangan kedaluwarsa, salah, atau sudah digunakan tidak dapat dipakai ulang. |
| Identitas pengirim berbeda | Salin ulang langsung dari laptop tujuan; aplikasi tidak menonaktifkan pemeriksaan sertifikat. |
| Kamera virtual tidak tersedia | Pasang backend OS, periksa izin, dan pastikan output tidak dipakai aplikasi lain. |
| Preview ada tetapi kamera tidak muncul di aplikasi lain | Pastikan mode Preview diagnostik tidak dicentang; mulai penerima sebelum membuka pemilih kamera. |
| Gambar berhenti | Periksa kamera/Wi-Fi dan mulai ulang sesi. Preview basi dikosongkan; output virtual mengirim hitam ketika frame basi. |

Tidak ada rekaman video atau penyimpanan undangan. Pengaturan tema dan path perangkat
virtual disimpan melalui QSettings. Sertifikat/kunci signaling bersifat sementara
untuk tiap sesi; identitas peer persisten dan discovery akan ditambahkan pada Tahap B.

## Pemeriksaan tanpa perangkat

```bash
.venv/bin/python -m unittest -v
.venv/bin/python -m camera_link.selftest --seconds 15
```

Pada Windows, ganti `.venv/bin/python` dengan `.\.venv\Scripts\python.exe`.
Self-test membuat sumber video sintetis 720p, mengirimkannya melalui koneksi WebRTC
lokal yang sebenarnya, dan melaporkan fps penerimaan serta CPU gabungan dua peer.
Secara default ia tidak membuka kamera virtual atau kamera fisik.

Untuk memeriksa backend virtual yang **sudah dipasang** di Linux:

```bash
.venv/bin/python -m camera_link.selftest --seconds 60 --virtual-camera --device /dev/video20
```

Pada Windows sebagai penerima uji lokal, gunakan `--virtual-camera` tanpa `--device`.
Selama tes berjalan, pilih kamera virtual dari aplikasi lain dan periksa pola
bergerak. Tes ini memisahkan masalah backend virtual dari capture kamera laptop.
Ia tidak membuktikan koneksi Wi-Fi atau dukungan lintas OS.

## Catatan pengujian 19 September 2026

- Linux, Python 3.14.7; tidak tersedia `/dev/video*` untuk pengujian perangkat nyata.
- 31 tes lulus dengan dependensi desktop: 19 tes logika/legacy dan 12 tes integrasi
  media/UI. Tanpa dependensi desktop, 19 tes lulus dan 12 integrasi dilewati.
- Video sintetis 1280×720 melalui WebRTC lokal: 450 frame dalam 15,00 detik,
  **30,00 fps**, CPU proses 55,5% (gabungan kedua peer, relatif satu inti).
- Output virtual diuji melalui pengganti `pyvirtualcam.Camera` di tes integrasi;
  bukan driver virtual OS sungguhan. Tes memeriksa frame hasil decode, penutupan
  device, frame basi menjadi hitam, pin sertifikat, replay, dan pembatalan sesi.
- Qt offscreen: startup, peran, tema, error input, penerimaan preview, dan tutup
  jendela. Tampilan kirim/terima juga diperiksa pada gambar hasil render.
- CI Ubuntu/Windows Python 3.12 disiapkan; hasil Windows belum tersedia di sesi ini.
- Belum diukur: kamera fisik, Wi-Fi dua mesin, driver nyata, latensi gerakan-ke-layar,
  pemakaian RAM jangka panjang, sesi 30 menit, audio, dan aksesibilitas OS menyeluruh.

## Formulir uji fisik berikutnya

Isi setelah laptop dan desktop tersedia:

| Item | Hasil |
| --- | --- |
| Versi Windows 11 / model kamera laptop | Belum diuji |
| Distro, kernel Linux, versi v4l2loopback | Belum diuji |
| IP/interface dan jenis koneksi (tanpa token undangan) | Belum dicatat |
| Kamera virtual terbaca di OBS | Belum diuji |
| Kamera virtual terbaca di aplikasi panggilan/browser | Belum diuji |
| Resolusi dan fps aktual, sesi 30 menit | Belum diuji |
| CPU/RAM pengirim dan penerima | Belum diuji |
| Latensi gerakan-ke-layar median/p95 | Belum diuji |
| Wi-Fi putus, stop, mulai ulang, sleep/resume | Belum diuji |
| Izin ditolak, kamera sibuk, perangkat dicabut | Belum diuji |

Gerbang Tahap A tetap terbuka sampai kamera laptop benar-benar bisa digunakan
aplikasi lain pada desktop. Audio dan penulisan ulang besar belum dimulai.
