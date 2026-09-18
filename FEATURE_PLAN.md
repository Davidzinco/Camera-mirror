# Rencana pengembangan Camera Mirror

Tanggal: 19 September 2026. Status: **rencana, belum diimplementasikan**.
Dokumen ini menjadi catatan acuan untuk pekerjaan berikutnya. Checklist berarti
pekerjaan yang harus dibuktikan, bukan kemampuan yang sudah tersedia.

## 1. Tujuan dan prioritas

| Prioritas | Fitur | Hasil yang diharapkan |
| --- | --- | --- |
| P0 — terpenting | Kamera laptop/komputer lain melalui Wi-Fi | PC desktop tanpa kamera bisa memilih kamera dari laptop di aplikasi panggilan atau OBS. |
| P1 | HP sebagai mikrofon | Suara mikrofon HP diterima komputer dan dapat dipilih sebagai input mikrofon oleh aplikasi lain. |
| P1 | Mikrofon komputer lain | Laptop/PC mengirim mikrofon ke komputer penerima melalui Wi-Fi. |
| P1 | UI lebih ramah dan dark mode | Alur pengirim/penerima jelas, pengaturan sederhana, status mudah dipahami. |
| P2 — jika memungkinkan | Speaker komputer lain sebagai output | Audio PC dikirim melalui Wi-Fi dan dimainkan di speaker laptop/PC penerima. |

Target aplikasi desktop: **Windows dan Linux**, termasuk koneksi silang OS.
MVP menggunakan jaringan lokal yang sama, tanpa akun atau layanan cloud.
Salah satu komputer boleh tersambung Ethernet asalkan dapat menjangkau peer di LAN.
Internet, banyak penerima sekaligus, dan relay bertingkat bukan syarat MVP.

Asumsi awal HP adalah Android, mengikuti proyek sekarang. iPhone belum termasuk
komitmen dukungan. Versi minimum Windows, distro Linux, arsitektur CPU, dan versi
dependensi ditetapkan setelah prototipe; jangan mengklaim semua versi OS didukung.

## 2. Kondisi kode saat ini

- UI memakai Tkinter/Pillow dengan warna terang di `camera_mirror.py`.
- `backend.py` mengirim kamera Android melalui scrcpy ke `/dev/video10` dan
  secara eksplisit memakai `--no-audio`.
- `wireless.py` menangani ADB Wi-Fi Android; ini belum menjadi protokol streaming
  atau penemuan komputer lain.
- `controller.py`, `phone_screen.py`, dan `setup_devices.py` bergantung pada
  systemd, WirePlumber, pkexec, dan v4l2loopback.
- `stream_service.py` memakai FIFO, `fcntl`, dan direktori runtime Linux.
- Sejumlah executable menggunakan path `/usr/bin/...`.

Artinya: mengganti warna atau membungkus aplikasi menjadi `.exe` saja belum
menghasilkan dukungan Windows. Lifecycle proses, perangkat virtual, penyimpanan,
dan penangkapan media harus memiliki implementasi per platform.

## 3. Keputusan teknologi sementara

**Pertahankan Python lebih dulu.** Hambatan utama adalah integrasi OS dan media,
bukan ekstensi `.py`. Pilihan berikut adalah kandidat untuk dibuktikan lewat
prototipe, bukan jaminan performa atau keputusan migrasi final.

| Bagian | Kandidat | Pertimbangan |
| --- | --- | --- |
| Aplikasi dan pengendali sesi | Python | Bisa mempertahankan logika yang masih berguna. |
| UI baru | PySide6/Qt | Kandidat UI Windows/Linux, tema terpusat, widget dan akses keyboard. |
| Media antarkomputer | WebRTC melalui aiortc | Mendukung audio/video; perlu uji codec, CPU, dan latensi nyata. |
| Capture dan konversi | PyAV/FFmpeg atau backend capture yang lolos uji | Enumerasi kamera/mikrofon dan format capture berbeda per OS. |
| Kamera virtual Linux | v4l2loopback + kandidat pyvirtualcam | Instalasi modul tetap merupakan dependensi sistem. |
| Kamera virtual Windows | Kandidat pyvirtualcam dengan backend OBS Virtual Camera | Membutuhkan komponen virtual camera terpasang; periksa konflik pemakaian dengan OBS. |
| Audio virtual Linux | PipeWire | Riset pembuatan source/sink dan routing yang dibersihkan saat sesi selesai. |
| Audio virtual Windows | Driver virtual audio yang tersedia, misalnya VB-CABLE | Aplikasi mengirim/menerima audio melalui endpoint driver; bukan membuat driver dengan Python. |
| Penemuan komputer | mDNS dan alamat manual | Tetap bisa terhubung ketika multicast diblokir. |

aiortc mendukung pertukaran audio/video, tetapi kemampuan codec dan akselerasi
hardware pada paket yang dipilih harus diuji. Jangan menjanjikan hardware encoding.
Jalur kamera Android lama tetap memakai scrcpy/ADB sebagai adapter tersendiri.

Jika hasil pengukuran menunjukkan bottleneck media, evaluasi GStreamer atau
helper native Rust/C++ pada bagian tersebut. Penulisan ulang seluruh aplikasi
hanya dipertimbangkan jika prototipe menunjukkan alasan nyata. Pergantian bahasa
tidak menghapus kebutuhan perangkat virtual atau driver OS.

## 4. Alur utama: kamera laptop untuk desktop

```text
Kamera bawaan/USB laptop
  -> capture di aplikasi pengirim
  -> encode dan kirim melalui Wi-Fi/LAN
  -> decode di aplikasi penerima pada desktop
  -> kamera virtual OS
  -> aplikasi panggilan / OBS / aplikasi pengguna
```

MVP memasang aplikasi pada kedua komputer. Laptop bertindak sebagai pengirim,
desktop sebagai penerima. Preview pada desktop hanya alat bantu; fitur baru
dianggap berhasil setelah aplikasi lain bisa memakai kamera virtualnya.

Alur UI: pilih **Bagikan kamera** di laptop, pilih **Gunakan kamera perangkat
lain** di desktop, temukan/pasangkan perangkat, pilih kamera, lalu mulai.
Gunakan satu sumber kamera dan satu penerima per sesi terlebih dahulu.
Default awal 720p 30 fps; 1080p menyusul setelah pengujian performa.

Jika “perantara” juga berarti HP -> laptop -> desktop, itu perlu tahap relay
terpisah. MVP memenuhi kamera yang terpasang pada laptop -> desktop terlebih
dahulu; relay menambah encoding, latensi, dan pengelolaan koneksi.

## 5. Mikrofon dan speaker

### Mikrofon HP

Target alur: mikrofon Android -> Wi-Fi -> komputer -> mikrofon virtual -> aplikasi.
Uji scrcpy `--audio-source=mic` sebagai jalur awal karena proyek sudah memakai ADB.
Opsi tersebut menyediakan capture mikrofon, tetapi tidak otomatis membuat input
mikrofon virtual di Windows/Linux. Prototipe harus membuktikan akses audio kontinu
dan routing-nya, bukan hanya rekaman file atau suara yang terdengar di speaker.

Mulai dari mode mikrofon saja, kemudian kamera + mikrofon bersamaan. Verifikasi
izin Android, versi yang sesuai, kondisi layar padam, dan perilaku saat koneksi
putus. Jangan sekadar menghapus `--no-audio` lalu menyatakan fitur selesai.
Jika jalur scrcpy tidak cocok untuk streaming/routing, evaluasi aplikasi pendamping
Android. Klien browser HP adalah alternatif riset dengan penyiapan secure context,
izin mikrofon, dan batasan background yang harus dibuktikan dahulu.

### Mikrofon laptop/komputer

Gunakan capture mikrofon lokal -> transport audio -> mikrofon virtual di penerima.
Sediakan pemilih sumber, indikator level, mute, dan tes input. Mikrofon HP dan
mikrofon laptop memakai keluaran virtual yang sama secara bergantian pada MVP.
Mixer banyak sumber belum termasuk.

### Speaker jarak jauh — opsional

Target: aplikasi pada PC -> output audio virtual PC -> jaringan -> speaker fisik
laptop/komputer lain. Pengguna memilih output virtual pada aplikasi/sistem asal.
Uji audio percobaan lebih dahulu, kemudian routing audio aplikasi sungguhan.
Memainkan bunyi uji saja belum memenuhi fitur output sistem.

Pisahkan tahap ini dari kamera. Audio dua arah membutuhkan penanganan gema,
feedback, jitter, dan perbedaan clock; jangan mengklaim echo cancellation hanya
karena menggunakan WebRTC. Monitoring mikrofon ke speaker mati secara default.
Jika driver/routing belum layak didistribusikan, tandai speaker sebagai eksperimen
dan tetap selesaikan rilis kamera. Cek lisensi redistribusi sebelum membundel driver.

## 6. Arsitektur yang dituju

- UI: menampilkan perangkat, preview, status, dan aksi pengguna.
- Pengendali sesi: mengatur state, intent mulai/stop, pemulihan, dan error.
- Adapter sumber: kamera lokal, mikrofon lokal, kamera/mikrofon Android.
- Transport: discovery, pairing, signaling, dan pengiriman media.
- Adapter keluaran: virtual camera, virtual microphone, dan speaker.
- Adapter platform: lifecycle worker, lokasi konfigurasi/log, izin, executable,
  serta instalasi/deteksi dependensi Windows atau Linux.

Capture, decode, dan jaringan tidak berjalan pada thread UI. Preview menyimpan
frame terbaru dengan antrean terbatas agar keterlambatan tidak terus bertambah.
Audio memakai buffer terbatas dengan timestamp; ukur sinkronisasi jika kamera dan
mikrofon aktif bersama.

Gunakan worker yang dapat dipantau di kedua OS. Definisikan perilaku menutup
jendela secara eksplisit; fungsi lama yang membiarkan kamera hidup perlu ditangani
dengan indikator/tray dan aksi stop yang jelas. Isolasi import khusus Linux supaya
aplikasi Windows tetap bisa dibuka tanpa `fcntl`, systemd, atau `/dev/video*`.

## 7. Koneksi dan kendali perangkat

- Discovery hanya menemukan perangkat; pengiriman kamera/mikrofon tetap perlu
  pairing serta tindakan mulai dari pengguna.
- Rancang pairing dengan token sekali pakai atau kode yang diverifikasi melalui
  kanal terlindungi; batasi percobaan dan kedaluwarsa sesi pairing.
- Autentikasi signaling dan ikat identitas peer ke sesi media. Enkripsi media
  WebRTC saja tidak menggantikan autentikasi perangkat.
- Simpan identitas perangkat tepercaya, bukan mengandalkan IP yang bisa berubah.
- Reconnect hanya ke perangkat yang sama dan hanya selama intent streaming masih
  aktif. Tombol stop membatalkan retry; jangan mengganti sumber secara diam-diam.
- Tampilkan bantuan untuk firewall, jaringan tamu/client isolation, atau izin
  kamera/mikrofon; sediakan IP manual ketika discovery gagal.
- Jangan merekam media atau mencatat token pairing secara default.

## 8. Rencana UI dark mode

Halaman utama menampilkan pilihan **Kirim** dan **Terima**, perangkat terpilih,
jenis media, preview/level mikrofon, serta satu aksi utama mulai/berhenti.
Gunakan istilah pengguna seperti “Bagikan kamera laptop” dan “Gunakan mikrofon HP”.

- Dark mode sebagai tampilan awal, dengan opsi terang/ikuti sistem jika backend
  mendukung. Pilihan tema disimpan.
- Warna terpusat untuk background, panel, teks, border, aksen, dan status.
- Status berupa teks dan ikon: mencari, menunggu izin, terhubung, mengirim,
  menerima, terputus. Warna bukan satu-satunya penanda.
- Pengaturan harian: perangkat, kamera/mikrofon, kualitas, mute, volume.
- Codec, alamat manual, log, dan pengaturan buffer berada di menu lanjutan.
- Error menyebut tindakan pemulihan yang relevan, tanpa menampilkan traceback
  sebagai pesan utama.
- Uji keyboard, fokus, ukuran font, scaling Windows/Linux, dan jendela kecil.

UI dasar dibangun bersama MVP kamera, lalu dipoles setelah alur perangkat stabil.

## 9. Tahapan dan kriteria selesai

### Tahap A — bukti kelayakan, prioritas kamera

- [ ] Enumerasi dan capture kamera lokal di Windows serta Linux.
- [ ] Kirim kamera antarkomputer lewat LAN dan tampilkan preview penerima.
- [ ] Teruskan frame ke kamera virtual pada masing-masing OS.
- [ ] Buktikan kamera dapat dipilih dan menampilkan gambar di aplikasi lain.
- [ ] Catat dependensi, konflik OBS, CPU/RAM, fps aktual, dan latensi terukur.
- [ ] Tetapkan versi OS/dependensi dan keputusan stack berdasarkan hasil.

Gerbang keberhasilan: kamera laptop benar-benar digunakan aplikasi di desktop
tanpa kamera. Keberhasilan preview saja tidak cukup untuk lanjut ke klaim MVP.

### Tahap B — fondasi lintas platform dan MVP kamera

- [ ] Pisahkan adapter OS dari logika bersama dan pertahankan jalur Android lama.
- [ ] Implementasikan pairing, discovery/IP manual, worker, stop, dan reconnect.
- [ ] Buat UI dasar dark mode dengan alur pengirim/penerima.
- [ ] Sediakan penyiapan dependensi dan paket yang diuji pada mesin bersih.
- [ ] Jalankan matriks koneksi silang OS di bawah ini.

### Tahap C — input suara

- [ ] Buktikan mikrofon Android masuk ke virtual microphone Linux dan Windows.
- [ ] Tambahkan mikrofon komputer melalui transport antarkomputer.
- [ ] Uji mute, input level, pemilihan perangkat, dan pemulihan koneksi.
- [ ] Uji kamera + mikrofon bersamaan beserta sinkronisasinya.

### Tahap D — penyempurnaan UI

- [ ] Lengkapi tema, onboarding, akses keyboard, pesan pemulihan, dan preferensi.
- [ ] Uji alur pertama pakai tanpa terminal selain instalasi dependensi yang perlu.

### Tahap E — output speaker opsional

- [ ] Prototipe output virtual -> jaringan -> speaker komputer tujuan.
- [ ] Uji aplikasi nyata, latensi, feedback, dan perangkat audio yang berganti.
- [ ] Putuskan siap rilis atau tetap eksperimen berdasarkan hasil pengujian.

## 10. Validasi sebelum menyatakan dukungan

| Pengirim | Penerima | Wajib diuji |
| --- | --- | --- |
| Windows | Windows | Kamera lokal -> virtual camera |
| Windows | Linux | Kamera lokal -> virtual camera |
| Linux | Windows | Kamera lokal -> virtual camera |
| Linux | Linux | Kamera lokal -> virtual camera |
| Android | Windows dan Linux | Mikrofon -> virtual microphone, lalu kamera + mic |

Untuk tiap pasangan desktop, ulangi pengujian audio setelah fitur tersedia.
Uji OBS dan setidaknya satu aplikasi panggilan/browser di masing-masing OS;
kompatibilitas satu aplikasi tidak membuktikan semua aplikasi kompatibel.

Target evaluasi awal: 720p/30 fps selama 30 menit tanpa crash atau penumpukan delay;
catat fps aktual dan latensi gerakan-ke-layar (median/p95), CPU/RAM, kondisi Wi-Fi,
serta spesifikasi perangkat. Angka tersebut adalah sasaran uji, bukan hasil saat ini.
Tetapkan ambang latensi layak setelah baseline tersedia sebelum rilis MVP.

Skenario gangguan: Wi-Fi putus/kembali, kamera sedang dipakai aplikasi lain,
perangkat dicabut, izin ditolak, dependensi tidak ada, firewall memblokir,
IP berubah, sleep/resume, stop saat reconnect, dan penutupan aplikasi.
Tes unit mencakup state sesi, validasi endpoint, identitas/pairing, dan preferensi;
CI Windows/Linux memeriksa import dan logika bersama. Tes perangkat virtual dan
media nyata tetap membutuhkan pengujian integrasi/hardware.

## 11. Referensi teknis

Referensi ditinjau untuk rencana ini; belum merupakan bukti bahwa implementasi
Camera Mirror sudah mendukung kemampuan tersebut.

- [aiortc: WebRTC audio/video untuk Python](https://github.com/aiortc/aiortc)
- [pyvirtualcam: backend dan kebutuhan virtual camera](https://github.com/letmaik/pyvirtualcam)
- [scrcpy: sumber audio termasuk mikrofon](https://github.com/Genymobile/scrcpy/blob/master/doc/audio.md)
- [Qt for Python: platform yang didukung](https://doc.qt.io/qtforpython-6/overviews/qtdoc-supported-platforms.html)
- [PipeWire: loopback dan virtual source/sink](https://docs.pipewire.org/page_module_loopback.html)
- [VB-CABLE: routing perangkat playback ke recording](https://vb-audio.com/Cable/)

## 12. Catatan untuk pekerjaan berikutnya

Mulai dari Tahap A; jangan memulai penulisan ulang besar atau driver sendiri
sebelum kamera laptop -> desktop terbukti bekerja. Perbarui checklist dengan
hasil pengujian dan batasan nyata. Pertanyaan yang dapat dipastikan menjelang
pengujian adalah versi OS/perangkat yang tersedia, Android atau iPhone, dan apakah
relay HP -> laptop -> desktop juga diperlukan. Asumsi di atas cukup untuk memulai
prototipe tanpa menunda prioritas kamera.
