# Camera Mirror — port Rust

Workspace Rust untuk menggantikan aplikasi Python secara bertahap. Tujuannya
bukan menulis ulang semuanya sekaligus, tetapi memindahkan lapisan demi lapisan
sambil tetap memakai aplikasi yang sudah berjalan.

## Status

| Bagian | Python | Rust |
| --- | --- | --- |
| Format undangan `cm1:` | ✅ | ✅ kompatibel |
| Gate pairing satu kali pakai | ✅ | ✅ |
| Preferensi atomik | ✅ | ✅ |
| Deteksi HP ADB | ✅ | ✅ |
| Pairing wireless (kode 6 angka) | ✅ | ✅ |
| USB → Wi-Fi (`adb tcpip`) | ✅ | ✅ |
| Validasi kamera + scrcpy | ✅ | ✅ |
| Menjalankan/menghentikan kamera | ✅ | ✅ |
| Kamera laptop ⇄ PC (WebRTC) | ✅ | ⏳ tahap 2 |
| Kamera virtual Windows/Linux | ✅ | ⏳ tahap 2 |
| Pratinjau di dalam aplikasi | ✅ | ✅ (Windows) | tahap 3 (Linux decode) |
| Pemadaman layar HP | ✅ | ⏳ tahap 3 |
| Auto-reconnect mDNS | ✅ | ⏳ tahap 3 |

Sampai tahap 2 selesai, gunakan aplikasi Python untuk mode **Kamera Laptop ke
PC**. Kedua aplikasi memakai format undangan yang sama, sehingga nanti dapat
saling terhubung.

## Menjalankan

```bash
cd rust
cargo run -p camera-mirror-app
```

Prasyarat:

- Rust 1.85 atau lebih baru (diuji dengan 1.99).
- Windows: MSVC Build Tools **atau** toolchain GNU + MinGW-w64. Untuk GNU:
  ```powershell
  rustup toolchain install stable-x86_64-pc-windows-gnu
  rustup default stable-x86_64-pc-windows-gnu
  winget install BrechtSanders.WinLibs.POSIX.UCRT
  ```
- Linux: `libxkbcommon`, driver OpenGL, dan `pkg-config` untuk build GUI.
  Untuk kamera HP: `scrcpy`, `android-tools`, `v4l2loopback-dkms`.
- Android: Debugging USB aktif dan Android 12+.

## Tes

```bash
cd rust
cargo test --workspace
```

Tes mencakup roundtrip undangan yang identik dengan Python, gate pairing,
preferensi atomik, parsing ADB, pemilihan FPS kamera, dan keamanan argumen
pairing (kode tidak pernah masuk argv).

## Pemecahan masalah

- **Windows: aplikasi langsung tertutup dengan kode `0xc0000005`.** Driver Vulkan
  Intel lama (`igvk64.dll`) dapat crash saat wgpu memilih adapter. Build Windows
  kini tidak menawarkan Vulkan secara default dan memakai Direct3D 12; jalankan
  `cargo run -p camera-mirror-app` lagi. Jika Anda memang ingin Vulkan, set
  `WGPU_BACKEND=vulkan` secara eksplisit untuk melihat apakah driver sudah diperbarui.
- **Build Windows gagal pada tahap link.** Pastikan PATH memuat `%USERPROFILE%\.cargo\bin`
  dan folder `mingw64\bin` dari WinLibs bila memakai toolchain GNU.
- **Pratinjau tidak muncul di kotak.** Di Windows pratinjau adalah jendela scrcpy
  yang dipindahkan ke dalam jendela aplikasi. Jendela itu baru ada 1–3 detik
  setelah scrcpy mulai; tunggu sebentar. Kalau tetap kosong, buka **Log kamera**
  dan pastikan tidak ada galat. Di Linux, gambar masuk ke `/dev/video10`
  (`v4l2loopback`) dan tidak ditampilkan di kotak.
- **HP USB ditandai `[WIFI]`.** Sudah diperbaiki: mode kini dibaca dari serial.
  Setelah memperbarui, klik **Cari ulang HP** agar daftar dimuat ulang.

## Struktur

```text
rust/
  crates/
    camera-mirror-core/   # tanpa GUI, tanpa async runtime
      src/invitation.rs   # format cm1 + validasi
      src/gate.rs         # token acak, TTL, batas percobaan
      src/frames.rs       # mailbox satu frame terbaru
      src/preferences.rs  # JSON atomik, izin 0600 di Unix
      src/android/        # Runner, ADB, scrcpy, wireless, proses
    camera-mirror-app/    # GUI egui/eframe
```

`Runner` adalah trait proses, sehingga seluruh lapisan ADB dapat diuji tanpa
perangkat atau program eksternal.

## Keputusan desain

- **Tanpa shell.** Semua perintah dijalankan sebagai argv, bukan string shell.
- **Kode pairing lewat stdin.** Tidak muncul di daftar proses atau log.
- **Proses scrcpy dimiliki aplikasi.** Output dibaca di thread terpisah agar UI
  tidak pernah menunggu pipe.
- **Tidak ada kunci preferensi yang tidak dikenal.** File rusak kembali ke
  default, penulisan memakai file sementara + rename.
- **egui/eframe.** Satu binary native, tanpa runtime web, dan tetap ringan di
  Windows/Linux.

## Rencana berikutnya

Lihat [docs/RUST_PORT.md](../docs/RUST_PORT.md) untuk parity matrix lengkap,
desain WebRTC/kamera virtual, dan risiko teknis.
