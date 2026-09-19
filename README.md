# Camera Mirror

Gunakan kamera laptop sebagai webcam desktop melalui Wi-Fi, atau kamera Android
sebagai webcam Linux. UI tersedia dalam tema gelap dengan kontrol ringkas.

## Instalasi mudah — mulai di sini

Unduh [ZIP versi main](https://github.com/Davidzinco/Camera-mirror/archive/refs/heads/main.zip),
lalu **ekstrak seluruh folder** ke lokasi yang ingin dipakai permanen. Tidak perlu
Git. Langkah berikut memasang mode kamera antarkomputer; koneksi internet dibutuhkan
saat unduhan dependensi pertama kali.

### Laptop Windows 11

1. Buka folder hasil ekstraksi dan klik dua kali **`Install-Windows.cmd`**.
2. Tunggu penyiapan selesai. Jika Python belum tersedia, installer mencoba
   memasang Python 3.12 64-bit melalui WinGet; ikuti persetujuan yang muncul.
3. Aplikasi terbuka. Pilih **Kirim kamera** untuk membagikan kamera laptop.

Selanjutnya buka **Camera Mirror** dari Start Menu, atau klik kembali file yang
sama. Paket yang sudah siap digunakan kembali. Jendela terminal menampilkan
progres/error dan tetap terbuka selama aplikasi berjalan.

Jika WinGet tidak tersedia, pasang [Python untuk Windows](https://www.python.org/downloads/windows/)
64-bit versi 3.12, lalu klik installer lagi. Skrip memakai kebijakan eksekusi
PowerShell hanya untuk proses installer; tidak mengubah kebijakan sistem permanen.
**OBS tidak diperlukan pada laptop yang hanya mengirim kamera.**

### Desktop Linux

1. Buka folder hasil ekstraksi. Pada properti **`Install-Linux.sh`**, aktifkan
   **Allow executing as a program / Is executable** jika diperlukan.
2. Jalankan file tersebut dengan **Run in Terminal / Jalankan di terminal**.
3. Setelah penyiapan selesai, aplikasi terbuka. Selanjutnya pilih **Camera Mirror**
   dari menu aplikasi dan gunakan **Terima kamera**.

Perilaku klik file `.sh` berbeda menurut pengelola berkas. Jika file justru dibuka
sebagai teks, buka terminal pada folder hasil ekstraksi dan jalankan satu perintah:

```bash
bash Install-Linux.sh
```

Python 3 beserta dukungan `venv` harus tersedia. Installer membuat `.venv`, memasang
dependensi aplikasi, dan menambahkan pintasan pengguna; jalankan **tanpa sudo**.
Lokasi menu mengikuti `XDG_DATA_HOME` atau `~/.local/share/applications`.

### Penyiapan kamera virtual pada penerima — sekali di awal

Installer di atas memasang aplikasi. Agar gambarnya muncul sebagai webcam di OBS
atau aplikasi panggilan, komputer **penerima** juga memerlukan backend kamera virtual:

| Perangkat | Yang perlu disiapkan |
| --- | --- |
| Laptop Windows sebagai pengirim | Kamera fisik dan izin kamera Windows. |
| Desktop Linux sebagai penerima | `v4l2loopback`, header kernel yang sesuai, dan perangkat loopback. |
| Windows sebagai penerima (opsional) | OBS Studio beserta Virtual Camera; jangan jalankan output virtual OBS bersamaan. |

Untuk CachyOS/Arch, pasang `v4l2loopback-dkms`, `v4l2loopback-utils`, dan header
kernel aktif. [Panduan perangkat virtual Linux](docs/DESKTOP_CAMERA.md#desktop-linux)
menjelaskan pembuatan `/dev/video20` dan pemilihannya pada pengaturan aplikasi.
Langkah driver ini masih terpisah karena bergantung pada distro/kernel dan izin OS.

Sesudah siap: klik **Kirim kamera** di laptop → **Mulai bagikan kamera** → salin
undangan → tempel pada desktop dalam mode **Terima kamera** → **Hubungkan kamera**.
Kemudian pilih kamera virtual tersebut di aplikasi panggilan. Kedua komputer harus
berada pada LAN yang sama. Panduan lengkap ada di [kamera desktop](docs/DESKTOP_CAMERA.md).

### Masalah instalasi

- **Ubuntu/Debian: `venv` atau library Qt tidak tersedia.** Pasang prasyarat ini,
  lalu jalankan installer lagi:

  ```bash
  sudo apt update
  sudo apt install python3 python3-venv libegl1 libopengl0 libpulse0 libxkbcommon0 libxcb-cursor0
  ```

- **CachyOS/Arch: Python atau library Qt belum lengkap.** Paket dasar yang relevan:

  ```bash
  sudo pacman -S --needed python python-pip libglvnd libpulse libxkbcommon xcb-util-cursor
  ```

- **Unduhan gagal:** periksa internet/proxy, lalu jalankan installer lagi. Penyiapan
  yang gagal tidak ditandai selesai; pip menampilkan detail error pada terminal.
- **Windows memblokir skrip berdasarkan kebijakan organisasi:** gunakan instalasi
  manual dalam [panduan desktop](docs/DESKTOP_CAMERA.md#instalasi-aplikasi), atau
  minta pengelola perangkat menyiapkan dependensi. Installer bukan binary bertanda tangan.
- **Folder dipindahkan:** `.venv` dan pintasan menyimpan lokasi lokal. Buat penyiapan
  baru di lokasi tujuan; jangan menyalin `.venv` dari OS/folder lain.

### Memperbarui atau menghapus

Untuk memperbarui, tutup aplikasi dan ekstrak ZIP `main` terbaru ke folder yang
sama, atau jalankan `git pull` jika memakai Git. Klik installer lagi; perubahan
`requirements-desktop.txt` akan diperiksa dan dependensi disesuaikan bila perlu.

Untuk menghapus, tutup aplikasi, hapus folder hasil ekstraksi, dan hapus pintasan
**Camera Mirror** dari Start Menu atau berkas
`~/.local/share/applications/camera-mirror-desktop.desktop` (sesuaikan jika
`XDG_DATA_HOME` diatur). Python, OBS, dan modul kamera OS tidak dihapus oleh langkah ini.

## Status pengembangan

Rencana fitur kamera antarkomputer melalui Wi-Fi, mikrofon HP, audio, dukungan
Windows/Linux, dan UI dark mode dicatat di [FEATURE_PLAN.md](FEATURE_PLAN.md).
Prototipe kamera antarkomputer sudah tersedia; status tiap tahap ada di dokumen tersebut.

## Kamera laptop Windows 11 → desktop Linux (prototipe)

Jalankan `desktop_camera.py` untuk UI kirim/terima dengan tema gelap/terang.
Dependensi dan langkah pengujian ada di [panduan kamera desktop](docs/DESKTOP_CAMERA.md).
Output kamera virtual sudah memiliki adapter Windows/Linux, tetapi kamera fisik,
driver nyata, dan koneksi silang OS **belum teruji**. Mikrofon dan speaker belum
tersedia. Fitur Android/Linux yang sudah ada dijelaskan di bawah ini.

## Kamera Android pada Linux

Aplikasi desktop untuk memakai kamera Android sebagai webcam Linux. Tampilan
menggunakan tema gelap netral dengan kontrol ringkas dan aksen merah redup. Pengaturan utama cukup
**koneksi**, **kamera depan/belakang**, **kualitas**, dan **Mulai/Matikan kamera**.
Video diatur ke **30 fps**, sesuai preferensi pengguna dan kemampuan HP yang diuji.

## Mulai

### Instalasi dari source (CachyOS / Arch Linux)

Rilis awal: **v0.1.0**. Membutuhkan Python 3.10+, Android 12+, dan sesi desktop
Linux dengan systemd user. Platform utama yang diuji adalah CachyOS.

Pasang dependensi sistem:

```bash
sudo pacman -S --needed git python tk python-pillow scrcpy android-tools ffmpeg v4l2loopback-dkms v4l2loopback-utils polkit wireplumber
```

Pasang juga **header yang sesuai kernel aktif** agar DKMS dapat membangun modul
v4l2loopback. Penemuan Wi-Fi opsional membutuhkan paket `avahi` dan layanan Avahi
aktif. Versi scrcpy harus menyediakan opsi kamera dan `--keep-active` yang dipakai
aplikasi; periksa `scrcpy --help` bila fitur tidak tersedia.

```bash
git clone https://github.com/Davidzinco/Camera-mirror.git
cd Camera-mirror
python camera_mirror.py
```

Alternatif: unduh source ZIP atau tar.gz dari halaman Releases, ekstrak, lalu
jalankan `python camera_mirror.py` di folder hasil ekstraksi. Rilis source belum
memasang pintasan menu aplikasi secara otomatis. Jika pintasan sudah dibuat pada
komputer Anda, buka **Camera Mirror** dari menu aplikasi.

Pillow adalah satu-satunya dependensi Python pihak ketiga dan juga dicatat di
`requirements.txt`; Tkinter serta komponen webcam dipasang lewat pengelola paket
sistem. Layanan kamera dibuat otomatis menggunakan `systemd-run` saat digunakan.

### Kabel USB

1. Aktifkan USB debugging di HP dan izinkan komputer ini.
2. Sambungkan kabel. Aplikasi mendeteksi HP otomatis.
3. Klik **Mulai kamera**. Preview muncul di panel kanan.
4. Pilih **Android Webcam** di OBS, browser, atau aplikasi panggilan.

### Wi-Fi otomatis: penyiapan sekali lewat USB

1. Pastikan HP dan komputer berada di jaringan lokal yang sama.
2. Pilih **Wi-Fi → Hubungkan HP**.
3. Hubungkan satu HP lewat USB dan klik **Hubungkan otomatis**.
4. Setelah pesan berhasil muncul, kabel boleh dilepas.

Aplikasi mengambil alamat Wi-Fi HP, mengaktifkan ADB jaringan pada port 5555,
menghubungkan, memverifikasi identitas HP, dan menyimpan perangkat yang dikenal.
Tidak perlu menyalin IP atau memasukkan kode pairing untuk metode lewat USB ini.
Gunakan jaringan pribadi yang dipercaya. Android tetap meminta izin debugging
pertama kali; aplikasi tidak melewati izin tersebut.

Saat mode Wi-Fi dipilih dan aplikasi terbuka, koneksi yang disimpan dicoba kembali
secara otomatis. Jika kamera sebelumnya diminta berjalan, aplikasi juga mencoba
memulihkan stream setelah koneksi kembali. **Matikan kamera** membatalkan niat
untuk memulai stream lagi; kamera tidak otomatis dinyalakan hanya karena HP ditemukan.
Pemulihan tidak boleh memilih HP lain sebagai pengganti perangkat yang terputus.

Alamat perangkat disimpan dan diverifikasi lewat identitas hardware. Jika alamat
berubah, aplikasi juga mencoba penemuan mDNS/Avahi untuk perangkat yang dikenali.
Penemuan bergantung pada jaringan dan iklan layanan HP. Setelah HP reboot atau ADB
jaringan dimatikan, penyiapan USB mungkin perlu diulang. Tidak ada pemindaian semua
alamat jaringan. Koneksi ulang dapat dimatikan melalui **Pengaturan lanjutan**.

### Tanpa kabel USB sejak awal

Di panel wireless, klik **Tidak punya kabel USB?**. Buka Wireless debugging →
Pair device with pairing code di HP. **Cari HP di jaringan** mencoba mengisi alamat
pairing otomatis; bila jaringan tidak mendukung penemuan, isikan alamat dari HP.
Masukkan kode enam angka. Aplikasi mencoba menemukan alamat koneksi sesudah pairing.
Jika belum ditemukan, masukkan alamat koneksi dari halaman utama Wireless debugging
(port koneksi berbeda dari port pairing). Perangkat yang berhasil terhubung disimpan
untuk koneksi ulang berikutnya.

Kode pairing tidak disimpan. Kunci debugging dikelola ADB di `~/.android`.

## Preview dan respons gerakan

- Pembatasan preview 12 fps telah dihapus. Preview mengikuti stream 30 fps.
- FFmpeg menggunakan satu thread decoder untuk menghindari antrean antar-frame;
  tidak ada penambahan buffer scrcpy atau V4L2.
- Pembacaan JPEG dan pengecilan gambar dilakukan di thread terpisah dari GUI.
- Antrean preview menyimpan **satu frame terbaru**, sehingga frame lama tidak
  menumpuk saat komputer sibuk. Gambar basi disembunyikan setelah dua detik.
- Preview tetap terpisah dari input V4L2 yang dipakai OBS, sehingga tidak mengambil
  jatah pembaca V4L2 tambahan.

Kamera, encoder, jaringan, dan aplikasi tujuan tetap menambah waktu pemrosesan.
Optimasi ini bukan jaminan latensi nol. Untuk respons lebih baik gunakan **USB**
dan **Ringan · 720p**. Latensi gerakan dari objek nyata sampai layar belum diukur
secara kuantitatif.

Kamera normal Samsung SM-A566B melaporkan maksimum 30 fps. Uji permintaan 60 fps
pada kamera belakang 1080p menghasilkan sekitar 29,99 fps; aplikasi tidak menyajikan
angka 60 seolah-olah tercapai. Pengaturan harian kini tetap 30 fps.

## Pengaturan dan OBS

### Memadamkan layar HP saat kamera aktif

Gunakan tombol **Padamkan layar HP** di bawah preview. Tombol ini memadamkan
panel layar tanpa mengunci HP; scrcpy menjaga sesi Android tetap aktif supaya
kamera dan koneksi tidak masuk kondisi tidur. Tekan **Nyalakan layar HP** untuk
mengembalikannya. Pilihan ini diingat saat kamera dimulai lagi.

Tombol power fisik mengubah kondisi tidur/kunci HP, sehingga tidak sama dengan
mode ini dan pada perangkat yang diuji bertepatan dengan putusnya koneksi ADB.
Penghematan baterai belum diukur. HP tetap tidak terkunci ketika panel dipadamkan.

Layanan pendamping `camera-mirror-screen` memakai scrcpy tanpa audio/video,
`--keep-active` dan `--turn-screen-off`; di Android 15+ juga digunakan operasi
`cmd display power-off 0`. Layanan diikat ke `android-webcam` sehingga ikut berhenti
ketika kamera berhenti. Tidak ada pengaturan lock screen permanen yang diubah.

Referensi: https://github.com/Genymobile/scrcpy/blob/master/doc/device.md

### Perangkat webcam

- Kamera depan/belakang, kualitas, dan koneksi yang sudah tersedia diterapkan
  otomatis saat stream aktif; perubahan dapat memutus gambar sebentar.
- **Pengaturan lanjutan → Siapkan perangkat webcam** membuat `/dev/video10`
  (Android Webcam) dan `/dev/video11` (OBS Virtual Camera) jika belum ada.
  Biasanya dibutuhkan setelah reboot. Dialog administrator berasal dari sistem.
  Memulai kamera juga mencoba penyiapan bila perangkat belum tersedia.
- **Perbaiki deteksi aplikasi** menyegarkan WirePlumber. Ini bisa memutus audio
  desktop sesaat. Deteksi juga disegarkan setelah stream baru dimulai.
- Di OBS, input HP: **Video Capture Device (V4L2) → Android Webcam**.
  Untuk menyalurkan scene OBS, klik **Start Virtual Camera** di OBS dan pilih
  **OBS Virtual Camera** di aplikasi tujuan.
- Mikrofon memakai perangkat terpisah.
- Menutup panel membiarkan kamera berjalan. Gunakan **Matikan kamera** untuk stop.
  Penemuan/koneksi ulang otomatis hanya berjalan saat panel aplikasi terbuka.

## Berkas

- `camera_mirror.py`: tampilan dan alur interaksi.
- `controller.py`: validasi kemampuan HP serta mulai/stop layanan.
- `backend.py`: pembungkus ADB, scrcpy, dan systemd tanpa shell.
- `wireless.py`: penyiapan USB-ke-Wi-Fi, penemuan, dan koneksi ulang.
- `preferences.py`: penyimpanan pengaturan atomik di
  `~/.config/camera-mirror/preferences.json` (mengikuti `XDG_CONFIG_HOME`).
- `preview.py`: pembaca frame terbaru di thread terpisah.
- `stream_service.py`: scrcpy dan FFmpeg dalam layanan `android-webcam`.
- `setup_devices.py`: helper administrator untuk perangkat webcam.

Stream Matroska dialirkan melalui FIFO privat. Satu JPEG preview diperbarui secara
atomik di `$XDG_RUNTIME_DIR/camera-mirror/preview.jpg`, pada direktori runtime pengguna. JPEG dan FIFO dibersihkan ketika layanan berhenti. Tidak ada rekaman video
permanen. Log tersedia melalui **Bantuan → Log kamera**.

Dependensi CachyOS: `python`, `tk`, `python-pillow`, `scrcpy`, `android-tools`,
`ffmpeg`, `v4l2loopback-dkms`, `v4l2loopback-utils`, header kernel yang cocok,
`polkit`, sesi systemd user/WirePlumber, dan `avahi` untuk penemuan mDNS opsional.
Kamera langsung scrcpy membutuhkan Android 12+.

## Validasi

```bash
python -m unittest -v
```

Tes meliputi validasi koneksi, identitas HP, penyimpanan preferensi, dan parsing
kemampuan kamera. Penyiapan Wi-Fi melalui USB serta stream Wi-Fi berhasil diuji
langsung pada SM-A566B. Output JPEG baru terukur sekitar 29,8 fps. Rendering GUI
terbaru diuji dengan sumber lokal 30 fps dan mencapai sekitar 29,9 fps; ini bukan
pengukuran latensi kamera fisik. Tata letak diperiksa pada ukuran normal dan minimum.
Pemulihan Wi-Fi otomatis belum divalidasi ulang secara menyeluruh dengan HP fisik.

Referensi:
- https://github.com/Genymobile/scrcpy/blob/master/doc/connection.md
- https://github.com/Genymobile/scrcpy/blob/master/doc/camera.md
- https://developer.android.com/tools/adb#wireless
- https://android.googlesource.com/platform/packages/modules/adb/+/HEAD/docs/dev/adb_wifi.md

## Pengembangan dan laporan masalah

Jalankan `python -m unittest -v` sebelum mengirim perubahan. GitHub Actions
menjalankan tes unit dan pemeriksaan sintaks; pengujian perangkat Android, GUI,
dan V4L2 tetap membutuhkan perangkat fisik dan desktop Linux.

Laporkan masalah melalui tab Issues dengan versi aplikasi, distro/kernel, versi
Android dan scrcpy, cara reproduksi, serta log yang relevan. Hapus alamat IP,
serial perangkat, dan informasi pribadi dari log sebelum dibagikan.

Riwayat perubahan tersedia di [CHANGELOG.md](CHANGELOG.md).
