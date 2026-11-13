# Changelog

## Belum dirilis — Port Rust tahap 1

- Workspace Rust baru di `rust/` dengan dua crate: `camera-mirror-core` dan
  `camera-mirror-app`.
- Logika inti diport dan diuji ulang (36 tes Rust):
  - undangan `cm1:` yang kompatibel dengan Python, gate pairing satu kali pakai,
    mailbox frame terbaru, dan preferensi atomik;
  - lapisan perintah ADB/scrcpy tanpa shell, dengan timeout, deteksi program,
    parsing perangkat, pairing lewat stdin, serta validasi endpoint IPv4/IPv6;
  - pemilihan mode kamera, validasi FPS, dan pencegahan klaim 60 fps dari
    mode high-speed.
- GUI native egui untuk mode kamera HP Android: daftar perangkat, pengaturan
  kamera, pairing wireless, USB → Wi-Fi, mulai/berhenti scrcpy, log, dan tema.
- Windows: renderer wgpu memakai Direct3D 12, bukan Vulkan, untuk menghindari
  crash `0xc0000005` pada driver Vulkan Intel (`igvk64.dll`).
- Tombol **Mulai Kamera HP** kini dipin di bagian bawah halaman Android dan isi
  pratinjau dapat di-scroll, sehingga tombol tetap terlihat pada jendela pendek
  atau penskalaan tampilan tinggi.
- Pratinjau kamera HP tampil di dalam kotak pratinjau aplikasi Rust (Windows):
  jendela scrcpy di-reparent ke jendela egui, mengikuti posisi kotak saat
  digulir, dan disembunyikan saat dialog atau tab lain dibuka.
- Perbaikan USB → Wi-Fi: koneksi diulang sampai ±10 detik setelah `adb tcpip`,
  alamat IP dibaca dari interface mana pun yang memiliki IPv4 rute (bukan hanya
  `wlan0`), identitas HP memakai fallback `ro.boot.serialno`, pesan galat
  menyebut alamat yang dicoba, dan perangkat Wi-Fi langsung dipilih dengan label
  `[WIFI]` setelah berhasil.
- Perbaikan label mode perangkat: mode ditentukan dari serial (`IP:port` berarti
  Wi-Fi), sehingga HP yang tersambung lewat USB tidak lagi ditandai `[WIFI]`.
- Pekerjaan ADB dan scrcpy berjalan di thread latar sehingga UI tidak membeku.
- Mode kamera laptop ⇄ PC dan kamera virtual menyusul pada tahap 2; aplikasi
  Python tetap menjadi jalur utama sampai parity tercapai.
- Dokumentasi: `rust/README.md` dan `docs/RUST_PORT.md` (parity matrix, desain
  WebRTC/kamera virtual, risiko).
- Perbaikan installer Python: pemeriksaan dependensi kini menunggu lebih lama
  (180 detik, dua percobaan) untuk impor pertama yang lambat di Windows, mengimpor
  Qt sebelum `pyvirtualcam` (urutan sebaliknya membuat CPython Windows crash), dan
  menampilkan pesan pemulihan yang jelas.
- Perbaikan deteksi alat Android: pencarian di folder paket WinGet hanya menerima
  nama executable yang tepat, sehingga `scrcpy-server` tidak lagi terpilih sebagai
  pengganti `scrcpy.exe`; petunjuk instalasi kini membedakan `scrcpy` dan
  `Google.PlatformTools`.

## Belum dirilis — Dukungan Kamera Android di Windows & UI Berpindah Mode Cepat

- **Dukungan Kamera Android di Windows**:
  - Fitur kamera HP Android (via ADB dan `scrcpy`) kini dapat digunakan di Windows maupun Linux.
  - Pencarian otomatis lokasi binary `scrcpy` dan `adb` di Windows (PATH, Android SDK, WinGet install dir, atau folder program).
  - Manajemen proses streaming mandiri tanpa ketergantungan pada Linux `systemd`, `fcntl`, atau `mkfifo`.
  - Pemadaman layar HP (`phone_screen`) dan konversi nirkabel satu-klik (`adb tcpip 5555`) kini berjalan lancar di Windows.
- **Peningkatan UI (Mode Switching 1-Klik)**:
  - Antarmuka terpadu modern berbasis PySide6 dengan tombol pemilihan mode di bagian atas:
    - **`💻 Kamera Laptop ke PC (Wi-Fi)`**: Kirim dan terima kamera antarkomputer melalui WebRTC LAN.
    - **`📱 Kamera HP Android ke PC`**: Deteksi perangkat USB/Wi-Fi, pemilihan kamera depan/belakang, resolusi, FPS, dan opsi hemat daya padam layar.
  - Berpindah mode cukup dengan sekali klik tanpa perlu membuka jendela terpisah.
  - Tombol pemeriksaan status ketersediaan ADB & scrcpy dan dialog bantuan instalasi.
- **Pembaruan Kompatibilitas & Pengujian**:
  - Semua 39 tes unit dan integrasi lulus di Windows dan Linux.
  - `camera_mirror.py` kini langsung membuka UI modern terpadu secara default.

## Belum dirilis — prototipe kamera desktop

- Installer sumber yang dapat diklik pada Windows/Linux, penyiapan `.venv`,
  pemasangan Python melalui WinGet bila diperlukan di Windows, dan pintasan menu.
- README memprioritaskan instalasi mudah serta menjelaskan penyiapan driver terpisah.
- CI Ubuntu memasang library runtime Qt yang sebelumnya menyebabkan import gagal;
  workflow desktop juga memeriksa installer dan pemakaian ulang lingkungan.

- Kamera antarkomputer melalui WebRTC LAN, capture Qt, dan adapter virtual camera
  v4l2loopback Linux / OBS Windows. Pembuktian hardware dan silang OS masih menunggu.
- Pairing undangan sementara dengan HTTPS/pin sertifikat, satu penerima, dan stop
  yang melepaskan koneksi serta keluaran virtual.
- UI desktop dark/light mode, alur Kirim/Terima, preview, dan bantuan penyiapan.
- UI Android lama memakai warna gelap dan memiliki pintasan ke kamera komputer.
- Tes media/UI sintetis, self-test transport, dan job CI desktop Ubuntu/Windows.
- Audio, discovery komputer, reconnect otomatis, dan installer binary mandiri belum tersedia.

## v0.1.0 — 2026-09-14

Rilis awal Camera Mirror untuk desktop Linux (CachyOS / Arch Linux).

### Fitur

- Kamera Android sebagai webcam V4L2 melalui USB atau Wi-Fi.
- Pilihan kamera depan/belakang, 720p/1080p, dan stream 30 fps.
- Preview terintegrasi dengan antrean satu frame terbaru.
- Penyiapan Wi-Fi lewat USB, pairing wireless, serta penemuan mDNS opsional.
- Koneksi ulang dengan verifikasi identitas HP dan pengaturan tersimpan.
- Kontrol panel layar HP selama sesi kamera aktif.
- Penyiapan Android Webcam dan OBS Virtual Camera melalui dialog administrator.
- Layanan systemd user yang mempertahankan stream ketika panel ditutup.

### Distribusi dan validasi

- Panduan instalasi, daftar dependensi Python, dan pengabaian berkas lokal.
- GitHub Actions untuk tes unit dan pemeriksaan sintaks.
- 13 tes unit lulus pada penyiapan rilis.

### Batasan

- Memerlukan Android 12+, scrcpy dengan opsi yang digunakan aplikasi, dan
  modul v4l2loopback sesuai kernel aktif.
- Distribusi berupa source; belum tersedia installer atau binary mandiri.
- Pemulihan Wi-Fi menyeluruh pada perangkat fisik dan latensi kamera belum
  divalidasi ulang dalam penyiapan rilis ini.
- Mikrofon menggunakan perangkat terpisah.
