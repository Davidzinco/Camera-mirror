# Changelog

## Belum dirilis — prototipe kamera desktop

- Kamera antarkomputer melalui WebRTC LAN, capture Qt, dan adapter virtual camera
  v4l2loopback Linux / OBS Windows. Pembuktian hardware dan silang OS masih menunggu.
- Pairing undangan sementara dengan HTTPS/pin sertifikat, satu penerima, dan stop
  yang melepaskan koneksi serta keluaran virtual.
- UI desktop dark/light mode, alur Kirim/Terima, preview, dan bantuan penyiapan.
- UI Android lama memakai warna gelap dan memiliki pintasan ke kamera komputer.
- Tes media/UI sintetis, self-test transport, dan job CI desktop Ubuntu/Windows.
- Audio, discovery komputer, reconnect otomatis, dan installer belum tersedia.

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
