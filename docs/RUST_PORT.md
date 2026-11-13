# Rencana port Rust

Dokumen ini menjelaskan bagaimana aplikasi Python dipindahkan ke Rust tanpa
kehilangan fitur atau memaksa pengguna pindah sebelum siap.

## Prinsip

1. **Tidak ada big-bang rewrite.** Setiap tahap harus dapat dijalankan dan diuji.
2. **Format tetap kompatibel.** Undangan `cm1:` dipertahankan, sehingga versi
   Python dan Rust dapat saling terhubung selama masa transisi.
3. **Keamanan tidak diturunkan.** Pin sertifikat, token satu kali pakai, dan
   validasi input dipertahankan di setiap tahap.
4. **Satu sumber kebenaran.** Logika non-GUI berada di `camera-mirror-core`,
   bukan di dalam handler UI.

## Tahap 1 — fondasi dan mode Android (selesai)

Sudah diport dan diuji:

- `Invitation` encode/decode dengan validasi IPv4, port, fingerprint, token.
- `PairingGate` dengan token acak 32 byte, TTL, batas percobaan, perbandingan
  waktu-konstan.
- `LatestFrame<T>` sebagai mailbox satu slot.
- `Preferences` atomik, maksimal 8 perangkat, izin `0600` di Unix.
- `Runner` proses tanpa shell, dengan timeout dan pembersihan pipe.
- Deteksi perangkat ADB, detail model/transport, pairing lewat stdin.
- Endpoint `IP:port` termasuk IPv6 dalam kurung.
- Perintah scrcpy kamera, parsing `--list-camera-sizes`, validasi FPS.
- `setup_usb` dan `reconnect` dengan verifikasi identitas hardware; `setup_usb`
  mengulang koneksi hingga sekitar 10 detik dan membaca alamat dari interface
  mana pun yang punya IPv4 rute.
- GUI egui: pemilihan HP, pengaturan kamera, pairing wireless, mulai/berhenti,
  log, preferensi tema.
- Pratinjau tertanam di jendela aplikasi (Windows): jendela scrcpy di-reparent
  ke jendela egui dengan `SetParent`, mengikuti kotak pratinjau saat digulir,
  dan disembunyikan saat tab lain atau dialog terbuka.

Yang sengaja belum ada di tahap ini:

- Pemadaman layar HP (`--keep-active`, `cmd display power-off`).
- Auto-reconnect saat aplikasi dibuka dengan mDNS/Avahi penuh.

## Tahap 2 — WebRTC dan kamera virtual

Ini bagian terbesar. Urutan yang disarankan:

1. **Signaling HTTPS + pin sertifikat**
   - `axum` atau `hyper` + `tokio-rustls`.
   - Sertifikat sementara lewat `rcgen`; fingerprint SHA-256 di undangan.
   - Endpoint `/offer` dan `/stop` dengan token Bearer dan `subtle` compare.
   - Batas ukuran body, timeout, dan satu penerima per sesi.
2. **Media**
   - `webrtc` (webrtc-rs) untuk PeerConnection, ICE tanpa STUN (LAN saja).
   - Capture kamera: `nokhwa` di Windows (Media Foundation) dan V4L2 di Linux.
   - Konversi frame ke `YUV420`/`I420` sesuai encoder.
   - Encoder: VP8/H.264 dari `webrtc` bila tersedia; alternatif `openh264`.
3. **Kamera virtual**
   - Linux: tulis frame ke `/dev/video10` memakai ioctl V4L2 output,
     `exclusive_caps=1`.
   - Windows: **risiko utama.** OBS Virtual Camera adalah filter DirectShow
     yang memakai DLL/modul OBS. Opsi:
     a. bind ke `obs-virtualcam-module64.dll` melalui `libloading` (perilaku
        yang sama dengan `pyvirtualcam`), atau
     b. dokumentasikan OBS Window Capture sebagai fallback, atau
     c. tulis filter DirectShow sendiri (proyek terpisah).
   - Keputusan akhir butuh pengujian pada mesin Windows dengan OBS terpasang.
4. **Lifecycle**
   - Satu `Session` per jendela, stop kooperatif, dan pembersihan resource
     saat jendela ditutup.
   - Status dan error yang dapat ditindaklanjuti, sama seperti versi Python.

Kriteria selesai:

- Laptop Windows mengirim kamera ke desktop Linux dan sebaliknya.
- Undangan dari aplikasi Python dapat dipakai aplikasi Rust dan sebaliknya.
- Kamera virtual muncul di OBS/Teams/Zoom.
- Tidak ada frame backlog saat CPU sibuk.

## Tahap 3 — parity dan distribusi

- Pratinjau lintas platform: decode H.264/JPEG di thread terpisah (Windows
  sudah memakai reparenting jendela scrcpy).
- Pemadaman layar HP dan penghematan baterai.
- Auto-reconnect penuh, termasuk mDNS/Avahi dan verifikasi identitas.
- Pilihan bahasa (Indonesia/Inggris) dengan modul i18n.
- Paket distribusi:
  - Windows: MSI/WiX atau `cargo-bundle`, plus pemeriksaan scrcpy/OBS.
  - Linux: binary + `.desktop` + `install.sh`.
- CI: `cargo fmt --check`, `cargo clippy`, `cargo test` di Ubuntu dan Windows.
- Tanda tangan binary dan pembaruan otomatis (opsional).

## Parity matrix

| Fitur | Python | Rust tahap 1 | Target |
| --- | --- | --- | --- |
| Undangan `cm1:` | ✅ | ✅ | ✅ |
| Pairing satu kali | ✅ | ✅ | ✅ |
| Preferensi | ✅ | ✅ | ✅ |
| ADB discover | ✅ | ✅ | ✅ |
| Wireless pairing | ✅ | ✅ | ✅ |
| USB → Wi-Fi | ✅ | ✅ | ✅ |
| Kamera scrcpy | ✅ | ✅ | ✅ |
| WebRTC LAN | ✅ | — | tahap 2 |
| Kamera virtual Linux | ✅ | — | tahap 2 |
| Kamera virtual Windows | ✅ | — | tahap 2 |
| Pratinjau aplikasi | ✅ | ✅ (Windows) | Linux: jendela scrcpy |
| Layar HP mati | ✅ | — | tahap 3 |
| mDNS reconnect | ✅ | sebagian | tahap 3 |
| i18n | — | — | tahap 3 |
| GUI tema gelap/terang | ✅ | ✅ | ✅ |

## Risiko

| Risiko | Dampak | Mitigasi |
| --- | --- | --- |
| Virtual camera Windows | Tinggi | Uji `libloading` pada DLL OBS; sediakan fallback Window Capture |
| API `webrtc` berubah | Sedang | Kunci versi, tes integrasi loopback |
| Build GUI Linux butuh library sistem | Rendah | Dokumentasikan paket apt/pacman, CI memasangnya |
| Perbedaan codec | Sedang | Negosiasi H.264/VP8, uji kedua arah |
| Pengguna beralih terlalu dini | Sedang | UI menyatakan mode mana yang sudah aktif |

## Cara berkontribusi

1. Tambahkan tes di `camera-mirror-core` untuk logika baru.
2. Jangan menaruh panggilan proses langsung di handler UI; gunakan `Runner`
   dan thread latar dengan channel.
3. Jaga pesan error tetap dapat ditindaklanjuti dan sebutkan langkah berikutnya.
4. Jalankan `cargo fmt` dan `cargo test --workspace` sebelum commit.
