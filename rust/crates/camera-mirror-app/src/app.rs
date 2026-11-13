//! Application state, background jobs and the egui interface.

use camera_mirror_core::android::{
    CameraRequest, CameraSession, DeviceInfo, DeviceMode, Facing, FrameRate, FrameSize, Platform,
    ProcessRunner, adb, camera, wireless,
};
use camera_mirror_core::preferences::Preferences;
use camera_mirror_core::{APP_NAME, VERSION};
use eframe::egui::{self, Color32, RichText};
use std::sync::Arc;
use std::sync::mpsc::{self, Receiver, Sender};
use std::thread;

use crate::preview::{PhysicalRect, Preview};
use crate::theme::Theme;

const MUTED: Color32 = Color32::from_rgb(0xb0, 0xb0, 0xad);
const ERROR: Color32 = Color32::from_rgb(0xd6, 0x8a, 0x82);
const SUCCESS: Color32 = Color32::from_rgb(0x8f, 0xbf, 0x8f);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Tab {
    Laptop,
    Android,
}

enum Message {
    Devices(Vec<DeviceInfo>),
    Tools {
        adb: bool,
        scrcpy: bool,
    },
    Preflight {
        request: CameraRequest,
        result: Result<(), String>,
    },
    Stopped,
    Pair(Result<String, String>),
    Connect(Result<String, String>),
    Wifi(Result<(String, Preferences), String>),
    Reconnected(Option<String>),
}

struct Tools {
    adb: bool,
    scrcpy: bool,
    checked: bool,
}

pub struct CameraMirrorApp {
    preferences: Preferences,
    theme: Theme,
    tab: Tab,
    session: Arc<CameraSession>,
    sender: Sender<Message>,
    receiver: Receiver<Message>,
    devices: Vec<DeviceInfo>,
    selected_device: usize,
    facing: Facing,
    size: FrameSize,
    fps: FrameRate,
    tools: Tools,
    status: String,
    status_error: bool,
    busy: bool,
    refreshing: bool,
    active_serial: Option<String>,
    pairing_address: String,
    pairing_code: String,
    logs_open: bool,
    about_open: bool,
    dirty: bool,
    preview: Preview,
    preview_rect: Option<egui::Rect>,
    preview_clip: Option<egui::Rect>,
}

impl CameraMirrorApp {
    pub fn new(creation_context: &eframe::CreationContext<'_>) -> Self {
        let preferences = Preferences::load();
        let theme = Theme::from_preference(&preferences.theme);
        theme.apply(&creation_context.egui_ctx);
        let (sender, receiver) = mpsc::channel();
        let mut app = Self {
            facing: preferences.facing.parse().unwrap_or(Facing::Back),
            size: preferences.size.parse().unwrap_or(FrameSize::Fhd1080),
            fps: preferences.fps.parse().unwrap_or(FrameRate::Fps30),
            preferences,
            theme,
            tab: Tab::Android,
            session: Arc::new(CameraSession::new()),
            sender,
            receiver,
            devices: Vec::new(),
            selected_device: 0,
            tools: Tools {
                adb: false,
                scrcpy: false,
                checked: false,
            },
            status: "Siap. Pilih HP Android lalu klik Mulai Kamera HP.".into(),
            status_error: false,
            busy: false,
            refreshing: false,
            active_serial: None,
            pairing_address: String::new(),
            pairing_code: String::new(),
            logs_open: false,
            about_open: false,
            dirty: false,
            preview: Preview::new(),
            preview_rect: None,
            preview_clip: None,
        };
        app.check_tools();
        app.refresh_devices();
        app.reconnect_saved();
        app
    }

    fn persist(&mut self) {
        self.preferences.facing = self.facing.as_str().to_owned();
        self.preferences.size = self.size.as_str().to_owned();
        self.preferences.fps = self.fps.as_str().to_owned();
        self.preferences.theme = self.theme.as_preference().to_owned();
        if let Some(device) = self.devices.get(self.selected_device) {
            // Remember the hardware identity, not the DHCP address that may
            // change on the next network.
            self.preferences.last_device = self
                .preferences
                .wireless
                .iter()
                .find(|entry| entry.address == device.serial)
                .map(|entry| entry.serial.clone())
                .unwrap_or_else(|| device.serial.clone());
        }
        if let Err(error) = self.preferences.save() {
            self.session
                .push_log(format!("Preferensi gagal disimpan: {error}"));
        }
    }

    fn check_tools(&mut self) {
        let sender = self.sender.clone();
        thread::spawn(move || {
            let adb = camera_mirror_core::android::runner::find_executable("adb").is_file();
            let scrcpy = camera_mirror_core::android::runner::find_executable("scrcpy").is_file();
            let _ = sender.send(Message::Tools { adb, scrcpy });
        });
    }

    fn refresh_devices(&mut self) {
        if self.refreshing {
            return;
        }
        self.refreshing = true;
        self.status = "Mencari HP Android…".into();
        self.status_error = false;
        let sender = self.sender.clone();
        thread::spawn(move || {
            let runner = ProcessRunner::default();
            let devices = adb::device_details(&runner);
            let _ = sender.send(Message::Devices(devices));
        });
    }

    fn selected_device(&self) -> Option<&DeviceInfo> {
        self.devices.get(self.selected_device)
    }

    /// Add a freshly connected Wi-Fi phone to the list and select it.
    ///
    /// The list is not refreshed here on purpose: a background refresh would
    /// replace the success message before the user can read it.
    fn adopt_wireless(&mut self, address: &str, name: String) {
        if !self.devices.iter().any(|device| device.serial == address) {
            self.devices.push(DeviceInfo {
                serial: address.to_owned(),
                name,
                mode: DeviceMode::Wifi,
                authorized: true,
            });
        }
        if let Some(index) = self
            .devices
            .iter()
            .position(|device| device.serial == address)
        {
            self.selected_device = index;
        }
        self.dirty = true;
    }

    fn build_request(&self) -> Result<CameraRequest, String> {
        let device = self.selected_device().ok_or_else(|| {
            "Pilih perangkat HP Android yang terhubung terlebih dahulu.".to_owned()
        })?;
        if !device.authorized {
            return Err(
                "HP terdeteksi, tetapi perlu izin. Buka layar HP dan klik 'Izinkan USB debugging'."
                    .into(),
            );
        }
        CameraRequest::new(device.serial.clone(), self.facing, self.size, self.fps)
            .map(|request| request.with_preview(cfg!(windows)))
            .map_err(|error| error.to_string())
    }

    fn start_camera(&mut self) {
        if self.busy || self.session.active() {
            return;
        }
        let request = match self.build_request() {
            Ok(request) => request,
            Err(message) => {
                self.fail(message);
                return;
            }
        };
        self.busy = true;
        self.status = "Memeriksa kamera HP…".into();
        self.status_error = false;
        self.session.push_log(format!(
            "Memeriksa {} ({} / {} fps / {}).",
            request.serial,
            request.size.as_str(),
            request.fps.as_str(),
            request.facing.as_str()
        ));
        let sender = self.sender.clone();
        thread::spawn(move || {
            let runner = ProcessRunner::default();
            let result = camera::preflight(&runner, &request, Platform::current())
                .map_err(|error| error.to_string());
            let _ = sender.send(Message::Preflight { request, result });
        });
    }

    fn stop_camera(&mut self) {
        if self.busy {
            return;
        }
        self.preview.release();
        self.busy = true;
        self.status = "Menghentikan kamera HP…".into();
        self.status_error = false;
        let session = Arc::clone(&self.session);
        let sender = self.sender.clone();
        thread::spawn(move || {
            session.stop();
            let _ = sender.send(Message::Stopped);
        });
    }

    fn pair(&mut self) {
        if self.busy {
            return;
        }
        let address = self.pairing_address.trim().to_owned();
        let code = self.pairing_code.trim().to_owned();
        if address.is_empty() || code.is_empty() {
            self.fail(
                "Isi alamat IP:Port dan kode pairing 6 angka dari layar Wireless debugging HP.",
            );
            return;
        }
        self.busy = true;
        self.status = "Melakukan pairing wireless…".into();
        self.status_error = false;
        let sender = self.sender.clone();
        thread::spawn(move || {
            let runner = ProcessRunner::default();
            let result = adb::pair(&runner, &address, &code).map_err(|error| error.to_string());
            let _ = sender.send(Message::Pair(result));
        });
    }

    fn connect(&mut self) {
        if self.busy {
            return;
        }
        let address = self.pairing_address.trim().to_owned();
        if address.is_empty() {
            self.fail("Isi alamat IP:Port nirkabel HP.");
            return;
        }
        self.busy = true;
        self.status = format!("Menghubungkan ke {address}…");
        self.status_error = false;
        let sender = self.sender.clone();
        thread::spawn(move || {
            let runner = ProcessRunner::default();
            let result = adb::connect(&runner, &address).map_err(|error| error.to_string());
            let _ = sender.send(Message::Connect(result));
        });
    }

    fn setup_wifi(&mut self) {
        if self.busy {
            return;
        }
        let Some(device) = self.selected_device().cloned() else {
            self.fail("Hubungkan HP ke laptop/PC dengan kabel USB terlebih dahulu.");
            return;
        };
        if device.mode != DeviceMode::Usb {
            self.fail("Hubungkan HP ke laptop/PC dengan kabel USB terlebih dahulu.");
            return;
        }
        self.busy = true;
        self.status = "Mengalihkan HP ke mode Wi-Fi…".into();
        self.status_error = false;
        let mut preferences = self.preferences.clone();
        let sender = self.sender.clone();
        thread::spawn(move || {
            let runner = ProcessRunner::default();
            let result = wireless::setup_usb(&runner, &device, &mut preferences)
                .map(|address| (address, preferences))
                .map_err(|error| error.to_string());
            let _ = sender.send(Message::Wifi(result));
        });
    }

    fn reconnect_saved(&mut self) {
        if !self.preferences.auto_connect || self.preferences.wireless.is_empty() {
            return;
        }
        let preferences = self.preferences.clone();
        let sender = self.sender.clone();
        thread::spawn(move || {
            let runner = ProcessRunner::default();
            let connected = adb::device_details(&runner);
            let result = wireless::reconnect(&preferences, &connected, |address, expected| {
                wireless::connect_checked(&runner, address, Some(expected))
            });
            let _ = sender.send(Message::Reconnected(result));
        });
    }

    fn fail(&mut self, message: impl Into<String>) {
        self.status = message.into();
        self.status_error = true;
    }

    fn handle_message(&mut self) {
        while let Ok(message) = self.receiver.try_recv() {
            match message {
                Message::Devices(devices) => {
                    self.refreshing = false;
                    self.devices = devices;
                    if self.selected_device >= self.devices.len() {
                        self.selected_device = 0;
                    }
                    if let Some(index) = self
                        .devices
                        .iter()
                        .position(|device| device.serial == self.preferences.last_device)
                    {
                        self.selected_device = index;
                    }
                    let ready = self
                        .devices
                        .iter()
                        .filter(|device| device.authorized)
                        .count();
                    self.status = if self.devices.is_empty() {
                        "Tidak ada HP terdeteksi. Hubungkan kabel USB atau cek Wi-Fi.".into()
                    } else {
                        format!(
                            "Ditemukan {} HP ({ready} siap). Klik Mulai Kamera HP.",
                            self.devices.len()
                        )
                    };
                    self.status_error = false;
                }
                Message::Tools { adb, scrcpy } => {
                    self.tools = Tools {
                        adb,
                        scrcpy,
                        checked: true,
                    };
                }
                Message::Preflight { request, result } => {
                    self.busy = false;
                    match result {
                        Ok(()) => {
                            self.preview.release();
                            match self.session.start(&request, Platform::current()) {
                                Ok(()) => {
                                    self.active_serial = Some(request.serial.clone());
                                    self.status =
                                        "Kamera HP aktif. Gambar diteruskan ke webcam virtual."
                                            .into();
                                    self.status_error = false;
                                }
                                Err(error) => {
                                    self.session.push_log(error.to_string());
                                    self.fail(format!("Gagal memulai kamera: {error}"));
                                }
                            }
                        }
                        Err(message) => self.fail(message),
                    }
                }
                Message::Stopped => {
                    self.busy = false;
                    self.active_serial = None;
                    self.status = "Kamera HP dihentikan.".into();
                    self.status_error = false;
                    self.refresh_devices();
                }
                Message::Pair(result) => {
                    self.busy = false;
                    match result {
                        Ok(message) => {
                            self.status = message;
                            self.status_error = false;
                            self.pairing_code.clear();
                            self.refresh_devices();
                        }
                        Err(message) => self.fail(format!("Pairing gagal: {message}")),
                    }
                }
                Message::Connect(result) => {
                    self.busy = false;
                    match result {
                        Ok(_) => {
                            self.status = format!("Terhubung ke {}.", self.pairing_address.trim());
                            self.status_error = false;
                            self.refresh_devices();
                        }
                        Err(message) => self.fail(format!("Gagal terhubung: {message}")),
                    }
                }
                Message::Wifi(result) => {
                    self.busy = false;
                    match result {
                        Ok((address, preferences)) => {
                            let name = self
                                .selected_device()
                                .map(|device| device.name.clone())
                                .unwrap_or_else(|| address.clone());
                            self.preferences = preferences;
                            self.adopt_wireless(&address, name);
                            self.status = format!(
                                "Mode Wi-Fi berhasil. Terhubung ke {address}; kabel USB boleh dilepas."
                            );
                            self.status_error = false;
                        }
                        Err(message) => self.fail(format!("Gagal Wi-Fi: {message}")),
                    }
                }
                Message::Reconnected(result) => {
                    if let Some(address) = result {
                        let name = self
                            .preferences
                            .wireless
                            .iter()
                            .find(|device| device.address == address)
                            .map(|device| device.name.clone())
                            .unwrap_or_else(|| address.clone());
                        self.adopt_wireless(&address, name);
                        self.status = format!("Tersambung kembali ke {address}.");
                        self.status_error = false;
                    }
                }
            }
        }

        if self.active_serial.is_some() && !self.session.active() {
            self.active_serial = None;
            self.preview.release();
            // Show the last log line so a camera that fails to start explains
            // itself instead of only saying "stopped".
            let last = self
                .session
                .logs()
                .lines()
                .rev()
                .map(str::trim)
                .find(|line| !line.is_empty())
                .map(str::to_owned);
            self.status = match last {
                Some(line) => format!("Kamera HP berhenti: {line}"),
                None => "Kamera HP berhenti. Periksa log bila tidak disengaja.".into(),
            };
            self.status_error = true;
        }
    }

    fn header(&mut self, root: &mut egui::Ui) {
        let context = root.ctx().clone();
        egui::Panel::top("header").show(root, |ui| {
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                ui.heading(RichText::new(APP_NAME).strong());
                ui.label(RichText::new(format!("v{VERSION}")).color(MUTED));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui.button("Tentang").clicked() {
                        self.about_open = true;
                    }
                    egui::ComboBox::from_id_salt("theme")
                        .selected_text(self.theme.label())
                        .show_ui(ui, |ui| {
                            for theme in [Theme::Dark, Theme::Light] {
                                if ui
                                    .selectable_value(&mut self.theme, theme, theme.label())
                                    .changed()
                                {
                                    self.dirty = true;
                                    theme.apply(&context);
                                }
                            }
                        });
                });
            });
            ui.add_space(2.0);
            ui.horizontal(|ui| {
                let laptop = ui.selectable_label(self.tab == Tab::Laptop, "Kamera Laptop ke PC");
                if laptop.clicked() {
                    self.tab = Tab::Laptop;
                }
                let android =
                    ui.selectable_label(self.tab == Tab::Android, "Kamera HP Android ke PC");
                if android.clicked() {
                    self.tab = Tab::Android;
                }
                ui.add_space(8.0);
                ui.label(
                    RichText::new(match self.tab {
                        Tab::Laptop => "Berbagi kamera antarkomputer melalui WebRTC LAN",
                        Tab::Android => "HP Android sebagai webcam melalui USB atau Wi-Fi",
                    })
                    .color(MUTED),
                );
            });
            ui.add_space(2.0);
        });
    }

    fn status_bar(&self, root: &mut egui::Ui) {
        egui::Panel::bottom("status").show(root, |ui| {
            ui.horizontal_wrapped(|ui| {
                ui.label(RichText::new(&self.status).color(if self.status_error {
                    ERROR
                } else {
                    MUTED
                }));
                if self.busy {
                    ui.spinner();
                }
            });
        });
    }

    fn android_settings(&mut self, ui: &mut egui::Ui) {
        ui.heading("Perangkat HP Android");
        ui.label(
            RichText::new("Sambungkan HP via kabel USB (Debug USB aktif) atau Wi-Fi.").color(MUTED),
        );
        ui.horizontal(|ui| {
            let selected = self
                .selected_device()
                .map(device_label)
                .unwrap_or_else(|| "Tidak ada HP terdeteksi".into());
            egui::ComboBox::from_id_salt("android-device")
                .selected_text(selected)
                .width(ui.available_width() - 84.0)
                .show_ui(ui, |ui| {
                    for (index, device) in self.devices.iter().enumerate() {
                        let label = device_label(device);
                        if ui
                            .selectable_value(&mut self.selected_device, index, label)
                            .changed()
                        {
                            self.dirty = true;
                        }
                    }
                });
            if ui
                .add_enabled(!self.refreshing, egui::Button::new("Cari"))
                .clicked()
            {
                self.refresh_devices();
            }
        });
        if let Some(device) = self.selected_device() {
            if !device.authorized {
                ui.colored_label(
                    ERROR,
                    "HP perlu izin: buka layar HP, klik 'Izinkan USB debugging', lalu Cari lagi.",
                );
            }
        }
        ui.separator();

        ui.heading("Pengaturan kamera");
        ui.horizontal(|ui| {
            ui.label("Arah");
            egui::ComboBox::from_id_salt("facing")
                .selected_text(facing_label(self.facing))
                .show_ui(ui, |ui| {
                    for facing in [Facing::Back, Facing::Front] {
                        if ui
                            .selectable_value(&mut self.facing, facing, facing_label(facing))
                            .changed()
                        {
                            self.dirty = true;
                        }
                    }
                });
        });
        ui.horizontal(|ui| {
            ui.label("Resolusi");
            egui::ComboBox::from_id_salt("size")
                .selected_text(size_label(self.size))
                .show_ui(ui, |ui| {
                    for size in [FrameSize::Fhd1080, FrameSize::Hd720] {
                        if ui
                            .selectable_value(&mut self.size, size, size_label(size))
                            .changed()
                        {
                            self.dirty = true;
                        }
                    }
                });
        });
        ui.horizontal(|ui| {
            ui.label("Frame rate");
            egui::ComboBox::from_id_salt("fps")
                .selected_text(frame_rate_label(self.fps))
                .show_ui(ui, |ui| {
                    for fps in [FrameRate::Fps30, FrameRate::Fps60, FrameRate::Fps15] {
                        if ui
                            .selectable_value(&mut self.fps, fps, frame_rate_label(fps))
                            .changed()
                        {
                            self.dirty = true;
                        }
                    }
                });
        });
        ui.add_enabled(
            false,
            egui::Checkbox::new(
                &mut self.preferences.screen_off,
                "Padamkan layar HP (hemat baterai)",
            ),
        )
        .on_disabled_hover_text("Fitur ini menyusul pada port Rust.");
        ui.separator();

        ui.heading("Koneksi nirkabel");
        let usb_selected = self
            .selected_device()
            .is_some_and(|device| device.mode == DeviceMode::Usb);
        if ui
            .add_enabled(
                !self.busy && usb_selected,
                egui::Button::new("Jadikan Wi-Fi (dari USB)"),
            )
            .on_disabled_hover_text("Pilih perangkat yang tersambung lewat kabel USB.")
            .clicked()
        {
            self.setup_wifi();
        }
        ui.add_space(4.0);
        ui.add(
            egui::TextEdit::singleline(&mut self.pairing_address)
                .hint_text("IP:Port (contoh 192.168.1.5:38123)")
                .desired_width(f32::INFINITY),
        );
        ui.horizontal(|ui| {
            ui.add(
                egui::TextEdit::singleline(&mut self.pairing_code)
                    .hint_text("Kode 6 angka")
                    .desired_width(120.0),
            );
            if ui
                .add_enabled(!self.busy, egui::Button::new("Pair"))
                .clicked()
            {
                self.pair();
            }
            if ui
                .add_enabled(!self.busy, egui::Button::new("Hubungkan"))
                .clicked()
            {
                self.connect();
            }
        });
        ui.separator();

        ui.heading("Status alat");
        if !self.tools.checked {
            ui.label(RichText::new("Mengecek ketersediaan program…").color(MUTED));
        } else {
            ui.label(tool_label("ADB", self.tools.adb));
            ui.label(tool_label("scrcpy", self.tools.scrcpy));
            if !(self.tools.adb && self.tools.scrcpy) {
                ui.colored_label(
                    ERROR,
                    if cfg!(windows) {
                        "Pasang dengan: winget install Genymobile.scrcpy, lalu cek ulang."
                    } else {
                        "Pasang scrcpy & adb dari package manager distro Linux Anda."
                    },
                );
            }
            if ui.button("Cek ulang").clicked() {
                self.check_tools();
            }
        }
    }

    fn android_page(&mut self, ui: &mut egui::Ui) {
        // Pin the actions to the bottom so they stay reachable on short
        // windows and at high display scaling.
        egui::Panel::bottom("android-actions").show(ui, |ui| {
            ui.add_space(4.0);
            ui.horizontal_wrapped(|ui| {
                let active = self.session.active();
                let start = egui::Button::new(RichText::new("Mulai Kamera HP").strong())
                    .fill(ui.visuals().selection.bg_fill)
                    .min_size(egui::vec2(170.0, 32.0));
                if ui.add_enabled(!self.busy && !active, start).clicked() {
                    self.start_camera();
                }
                if ui
                    .add_enabled(
                        active,
                        egui::Button::new("Berhenti").min_size(egui::vec2(90.0, 32.0)),
                    )
                    .clicked()
                {
                    self.stop_camera();
                }
                if ui.button("Cari ulang HP").clicked() {
                    self.refresh_devices();
                }
            });
            ui.add_space(4.0);
        });

        egui::ScrollArea::vertical()
            .auto_shrink([false, false])
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.heading("Pratinjau & status HP Android");
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button("Log kamera").clicked() {
                            self.logs_open = true;
                        }
                    });
                });
                ui.add_space(4.0);

                let frame = egui::Frame::group(ui.style());
                let preview = frame.show(ui, |ui| {
                    ui.set_min_height(240.0);
                    ui.centered_and_justified(|ui| {
                        let text = if self.active_serial.is_some() {
                            if cfg!(windows) {
                                "Kamera HP aktif.\n\nMenampilkan pratinjau…"
                            } else {
                                "Kamera HP aktif.\n\nGambar tersedia di /dev/video10."
                            }
                        } else if self.busy {
                            "Menyiapkan kamera HP…"
                        } else {
                            "Kamera HP belum aktif.\n\nPilih perangkat, lalu klik Mulai Kamera HP."
                        };
                        ui.label(RichText::new(text).size(15.0).color(MUTED));
                    });
                    ui.clip_rect()
                });
                self.preview_rect = Some(preview.response.rect);
                self.preview_clip = Some(preview.inner);
                ui.add_space(8.0);
                let note = if cfg!(windows) {
                    "Pratinjau tampil langsung di kotak ini. Tutup dialog untuk melihatnya lagi."
                } else {
                    "Di Linux, scrcpy menulis ke /dev/video10 sehingga OBS dan aplikasi lain bisa \
                     memakainya."
                };
                ui.label(RichText::new(note).color(MUTED));
            });
    }

    fn drive_preview(&mut self, frame: &eframe::Frame, context: &egui::Context) {
        let Some(host) = host_window(frame) else {
            return;
        };
        if self.session.active() {
            if let Some(pid) = self.session.child_pid() {
                self.preview.attach(host, pid);
            }
        } else if self.preview.is_embedded() {
            self.preview.release();
        }
        let scale = context.pixels_per_point();
        // Dialogs are drawn by egui inside the same window, but the embedded
        // child window always paints on top of it, so hide it while one is open.
        let visible = self.tab == Tab::Android
            && self.active_serial.is_some()
            && !self.logs_open
            && !self.about_open;
        let visible = visible
            && match (self.preview_rect, self.preview_clip) {
                (Some(rect), Some(clip)) => {
                    let overlap = rect.intersect(clip).shrink(6.0);
                    overlap.width() >= 16.0 && overlap.height() >= 16.0
                }
                _ => false,
            };
        let rect = match (self.preview_rect, self.preview_clip) {
            (Some(rect), Some(clip)) if visible => {
                // Intersect with the scroll viewport so the picture never
                // spills outside the box, then stay clear of the frame border.
                let rect = rect.intersect(clip).shrink(6.0);
                PhysicalRect {
                    x: (rect.min.x * scale).round() as i32,
                    y: (rect.min.y * scale).round() as i32,
                    width: (rect.width() * scale).round() as i32,
                    height: (rect.height() * scale).round() as i32,
                }
            }
            _ => PhysicalRect {
                x: 0,
                y: 0,
                width: 1,
                height: 1,
            },
        };
        self.preview.place(rect, visible);
    }

    fn laptop_page(&mut self, ui: &mut egui::Ui) {
        ui.heading("Kamera Laptop ke PC (Wi-Fi)");
        ui.add_space(4.0);
        ui.label(
            RichText::new(
                "Mode WebRTC LAN sedang diport ke Rust (tahap 2). Sampai media pipeline \
                 selesai, mode ini tetap dilayani aplikasi Python yang sudah ada.",
            )
            .color(MUTED),
        );
        ui.add_space(10.0);
        egui::Frame::group(ui.style()).show(ui, |ui| {
            ui.heading("Yang perlu disiapkan");
            ui.label("1. Laptop: pilih Kirim kamera, kamera, dan IP Wi-Fi/LAN, lalu Mulai.");
            ui.label("2. Salin undangan melalui kanal pribadi ke desktop di LAN yang sama.");
            ui.label("3. Desktop: pilih Terima kamera, tempel undangan, lalu Hubungkan.");
            ui.label("4. Pilih kamera virtual pada aplikasi panggilan atau OBS.");
        });
        ui.add_space(10.0);
        ui.label(
            RichText::new(
                "Jalankan mode Python: python desktop_camera.py\n\
                 Port TCP pengirim (default 8765) dan trafik media UDP harus diizinkan firewall.",
            )
            .color(MUTED),
        );
        ui.add_space(10.0);
        if ui.button("Cek status tahap port Rust").clicked() {
            self.about_open = true;
        }
    }

    fn dialogs(&mut self, context: &egui::Context) {
        egui::Window::new("Log Kamera")
            .open(&mut self.logs_open)
            .default_size([680.0, 420.0])
            .show(context, |ui| {
                egui::ScrollArea::vertical()
                    .stick_to_bottom(true)
                    .show(ui, |ui| {
                        let logs = self.session.logs();
                        if logs.is_empty() {
                            ui.label(RichText::new("Belum ada catatan log.").color(MUTED));
                        } else {
                            ui.monospace(logs);
                        }
                    });
            });

        egui::Window::new("Tentang Camera Mirror")
            .open(&mut self.about_open)
            .default_width(460.0)
            .show(context, |ui| {
                ui.heading(format!("Camera Mirror v{VERSION}"));
                ui.label(RichText::new("Port Rust — tahap 1").color(MUTED));
                ui.add_space(8.0);
                ui.label(RichText::new("Sudah diport:").strong());
                ui.label("• Undangan cm1 dan gate pairing satu kali pakai");
                ui.label("• Penemuan perangkat ADB dan pairing wireless");
                ui.label("• Logika kamera scrcpy dan pengelolaan proses");
                ui.label("• Preferensi atomik dan pengingat perangkat");
                ui.add_space(8.0);
                ui.label(RichText::new("Berikutnya:").strong());
                ui.label("• WebRTC LAN + kamera virtual (Windows/Linux)");
                ui.label("• Perekaman video dan snapshot");
                ui.label("• Kontrol layar HP dan auto-reconnect penuh");
            });
    }
}

impl eframe::App for CameraMirrorApp {
    fn ui(&mut self, ui: &mut egui::Ui, frame: &mut eframe::Frame) {
        self.handle_message();
        ui.ctx()
            .request_repaint_after(std::time::Duration::from_millis(250));

        self.header(ui);
        self.status_bar(ui);

        if self.tab == Tab::Android {
            egui::Panel::left("android-settings")
                .resizable(false)
                .exact_size(330.0)
                .show(ui, |ui| {
                    egui::ScrollArea::vertical().show(ui, |ui| {
                        self.android_settings(ui);
                    });
                });
        }

        egui::CentralPanel::default().show(ui, |ui| match self.tab {
            Tab::Android => self.android_page(ui),
            Tab::Laptop => self.laptop_page(ui),
        });

        self.dialogs(ui.ctx());
        self.drive_preview(frame, ui.ctx());

        if self.dirty {
            self.persist();
            self.dirty = false;
        }
    }
}

impl Drop for CameraMirrorApp {
    fn drop(&mut self) {
        self.session.stop();
    }
}

/// Native window handle of the eframe window, used as the embedding parent.
#[cfg(windows)]
fn host_window(frame: &eframe::Frame) -> Option<isize> {
    use raw_window_handle::{HasWindowHandle, RawWindowHandle};
    match frame.window_handle().ok()?.as_raw() {
        RawWindowHandle::Win32(handle) => Some(handle.hwnd.get()),
        _ => None,
    }
}

#[cfg(not(windows))]
fn host_window(_frame: &eframe::Frame) -> Option<isize> {
    None
}

fn device_label(device: &DeviceInfo) -> String {
    let permission = if device.authorized {
        ""
    } else {
        " · perlu izin"
    };
    format!(
        "{} ({}) [{}{}]",
        device.name,
        device.serial,
        device.mode.as_str().to_ascii_uppercase(),
        permission
    )
}

fn facing_label(facing: Facing) -> &'static str {
    match facing {
        Facing::Back => "Kamera belakang (utama)",
        Facing::Front => "Kamera depan (selfie)",
    }
}

fn size_label(size: FrameSize) -> &'static str {
    match size {
        FrameSize::Fhd1080 => "1920 × 1080 (FHD)",
        FrameSize::Hd720 => "1280 × 720 (HD)",
    }
}

fn frame_rate_label(fps: FrameRate) -> &'static str {
    match fps {
        FrameRate::Fps15 => "15 FPS (hemat)",
        FrameRate::Fps30 => "30 FPS (standar)",
        FrameRate::Fps60 => "60 FPS (mulus)",
    }
}

fn tool_label(name: &str, available: bool) -> RichText {
    if available {
        RichText::new(format!("✔ {name} siap digunakan")).color(SUCCESS)
    } else {
        RichText::new(format!("✖ {name} belum terpasang")).color(ERROR)
    }
}
