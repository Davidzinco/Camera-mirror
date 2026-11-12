# Changelog

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
