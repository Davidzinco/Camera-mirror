//! scrcpy camera command construction and capability parsing.

use super::adb::devices;
use super::runner::{AndroidError, Result, Runner};
use regex::Regex;
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::sync::OnceLock;
use std::time::Duration;

pub const V4L2_DEVICE: &str = "/dev/video10";
pub const MIN_ANDROID_SDK: u32 = 31;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Platform {
    Windows,
    Linux,
    Other,
}

impl Platform {
    pub fn current() -> Self {
        if cfg!(windows) {
            Self::Windows
        } else if cfg!(target_os = "linux") {
            Self::Linux
        } else {
            Self::Other
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Facing {
    Back,
    Front,
}

impl Facing {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Back => "back",
            Self::Front => "front",
        }
    }
}

impl FromStr for Facing {
    type Err = AndroidError;

    fn from_str(value: &str) -> Result<Self> {
        match value {
            "back" => Ok(Self::Back),
            "front" => Ok(Self::Front),
            _ => Err(AndroidError::invalid("Arah kamera tidak valid.")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameSize {
    Hd720,
    Fhd1080,
}

impl FrameSize {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Hd720 => "1280x720",
            Self::Fhd1080 => "1920x1080",
        }
    }
}

impl FromStr for FrameSize {
    type Err = AndroidError;

    fn from_str(value: &str) -> Result<Self> {
        match value {
            "1280x720" => Ok(Self::Hd720),
            "1920x1080" => Ok(Self::Fhd1080),
            _ => Err(AndroidError::invalid("Resolusi kamera tidak valid.")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameRate {
    Fps15,
    Fps30,
    Fps60,
}

impl FrameRate {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Fps15 => "15",
            Self::Fps30 => "30",
            Self::Fps60 => "60",
        }
    }

    pub fn value(self) -> u32 {
        match self {
            Self::Fps15 => 15,
            Self::Fps30 => 30,
            Self::Fps60 => 60,
        }
    }
}

impl FromStr for FrameRate {
    type Err = AndroidError;

    fn from_str(value: &str) -> Result<Self> {
        match value {
            "15" => Ok(Self::Fps15),
            "30" => Ok(Self::Fps30),
            "60" => Ok(Self::Fps60),
            _ => Err(AndroidError::invalid("Kecepatan frame tidak valid.")),
        }
    }
}

/// One validated camera request.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CameraRequest {
    pub serial: String,
    pub facing: Facing,
    pub size: FrameSize,
    pub fps: FrameRate,
    pub preview: bool,
    pub v4l2_sink: Option<String>,
}

impl CameraRequest {
    pub fn new(
        serial: impl Into<String>,
        facing: Facing,
        size: FrameSize,
        fps: FrameRate,
    ) -> Result<Self> {
        let serial = serial.into();
        if serial.is_empty() || serial.starts_with('-') || serial.chars().any(char::is_whitespace) {
            return Err(AndroidError::invalid(
                "Pilih perangkat yang sudah terhubung.",
            ));
        }
        Ok(Self {
            serial,
            facing,
            size,
            fps,
            preview: false,
            v4l2_sink: None,
        })
    }

    pub fn with_preview(mut self, preview: bool) -> Self {
        self.preview = preview;
        self
    }

    pub fn with_v4l2_sink(mut self, sink: Option<String>) -> Self {
        self.v4l2_sink = sink;
        self
    }
}

/// Build the scrcpy arguments for camera-only streaming.
pub fn camera_command(scrcpy: &Path, request: &CameraRequest, platform: Platform) -> Vec<String> {
    let mut args = vec![
        scrcpy.display().to_string(),
        format!("--serial={}", request.serial),
        "--video-source=camera".into(),
        format!("--camera-facing={}", request.facing.as_str()),
        format!("--camera-size={}", request.size.as_str()),
        format!("--camera-fps={}", request.fps.as_str()),
        "--no-audio".into(),
        "--video-codec=h264".into(),
        "--video-buffer=0".into(),
    ];
    let sink = request.v4l2_sink.clone().or_else(|| {
        (platform == Platform::Linux && Path::new(V4L2_DEVICE).exists())
            .then(|| V4L2_DEVICE.to_owned())
    });
    let has_sink = sink.is_some();
    if let Some(sink) = sink {
        args.push(format!("--v4l2-sink={sink}"));
        args.push("--v4l2-buffer=0".into());
    }
    args.push("--window-title=Camera Mirror · Android Webcam".into());
    if !request.preview && (has_sink || platform != Platform::Windows) {
        args.push("--no-window".into());
    }
    args
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CameraMode {
    pub id: String,
    pub facing: String,
    pub fps: Vec<u32>,
    pub sizes: Vec<String>,
}

fn camera_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"--camera-id=(\S+)\s+\((back|front|external),.*?fps=\{([^}]+)\}")
            .expect("camera pattern is valid")
    })
}

fn size_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r"^\s+- (\d+x\d+)\s*$").expect("size pattern is valid"))
}

/// Parse `scrcpy --list-camera-sizes`. High-speed capture sections are skipped
/// so the app never claims a mode the normal camera path cannot deliver.
pub fn parse_camera_modes(output: &str) -> Vec<CameraMode> {
    let mut cameras: Vec<CameraMode> = Vec::new();
    let mut high_speed = false;
    for line in output.lines() {
        if let Some(captures) = camera_pattern().captures(line) {
            let fps = captures[3]
                .split(',')
                .filter_map(|value| value.trim().parse().ok())
                .collect();
            cameras.push(CameraMode {
                id: captures[1].to_owned(),
                facing: captures[2].to_owned(),
                fps,
                sizes: Vec::new(),
            });
            high_speed = false;
        } else if line.contains("High speed capture") {
            high_speed = true;
        } else if !high_speed {
            if let Some(captures) = size_pattern().captures(line) {
                if let Some(camera) = cameras.last_mut() {
                    camera.sizes.push(captures[1].to_owned());
                }
            }
        }
    }
    cameras
}

/// FPS values that the first camera with `facing` supports at `size`.
pub fn supported_fps(modes: &[CameraMode], facing: Facing, size: FrameSize) -> Vec<FrameRate> {
    let Some(camera) = modes.iter().find(|mode| mode.facing == facing.as_str()) else {
        return Vec::new();
    };
    if !camera.sizes.iter().any(|item| item == size.as_str()) {
        return Vec::new();
    }
    [FrameRate::Fps15, FrameRate::Fps30, FrameRate::Fps60]
        .into_iter()
        .filter(|rate| camera.fps.contains(&rate.value()))
        .collect()
}

pub fn camera_modes(runner: &dyn Runner, serial: &str) -> Result<Vec<CameraMode>> {
    let output = runner.run(
        &[
            "scrcpy".into(),
            format!("--serial={serial}"),
            "--list-camera-sizes".into(),
        ],
        None,
        Duration::from_secs(15),
    )?;
    let modes = parse_camera_modes(&output);
    if modes.is_empty() {
        return Err(AndroidError::invalid(
            "Kemampuan kamera belum terbaca. Coba cari HP lagi.",
        ));
    }
    Ok(modes)
}

/// Verify everything before a long-running scrcpy process is spawned.
pub fn preflight(runner: &dyn Runner, request: &CameraRequest, platform: Platform) -> Result<()> {
    if !devices(runner)?
        .iter()
        .any(|serial| serial == &request.serial)
    {
        return Err(AndroidError::invalid(
            "HP belum terhubung. Sambungkan kabel atau pilih Hubungkan HP.",
        ));
    }
    let modes = camera_modes(runner, &request.serial)?;
    if !supported_fps(&modes, request.facing, request.size).contains(&request.fps) {
        return Err(AndroidError::invalid(format!(
            "{} fps pada resolusi ini tidak tersedia di kamera HP. Pilih 30 fps atau resolusi lain.",
            request.fps.as_str()
        )));
    }
    if platform == Platform::Linux && !Path::new(V4L2_DEVICE).exists() {
        return Err(AndroidError::invalid(format!(
            "{V4L2_DEVICE} belum tersedia. Jalankan penyiapan perangkat webcam terlebih dahulu."
        )));
    }
    let sdk = runner
        .run(
            &[
                "adb".into(),
                "-s".into(),
                request.serial.clone(),
                "shell".into(),
                "getprop".into(),
                "ro.build.version.sdk".into(),
            ],
            None,
            Duration::from_secs(10),
        )
        .unwrap_or_default();
    if let Ok(sdk) = sdk.trim().parse::<u32>() {
        if sdk < MIN_ANDROID_SDK {
            return Err(AndroidError::invalid(
                "Kamera HP membutuhkan Android 12 atau lebih baru.",
            ));
        }
    }
    Ok(())
}

/// Default scrcpy path used by the UI preview text.
pub fn scrcpy_hint() -> PathBuf {
    PathBuf::from("scrcpy")
}

#[cfg(test)]
mod tests {
    use super::*;

    const CAMERAS: &str = r#"
    --camera-id=0    (back, 4080x3060, fps={15, 20, 24, 30}, zoom-range=[1, 8])
        - 1920x1080
        - 1280x720
      High speed capture (--camera-high-speed):
        - 1280x720 (fps={120, 240})
    --camera-id=1    (front, 4000x3000, fps={15, 30, 60})
        - 1920x1080
"#;

    fn request(serial: &str) -> CameraRequest {
        CameraRequest::new(serial, Facing::Back, FrameSize::Fhd1080, FrameRate::Fps30).unwrap()
    }

    #[test]
    fn rejects_invalid_serial_before_start() {
        assert!(
            CameraRequest::new(
                "--tcpip",
                Facing::Back,
                FrameSize::Fhd1080,
                FrameRate::Fps30
            )
            .is_err()
        );
        assert!(
            CameraRequest::new("", Facing::Back, FrameSize::Fhd1080, FrameRate::Fps30).is_err()
        );
        assert!(
            CameraRequest::new("a b", Facing::Back, FrameSize::Fhd1080, FrameRate::Fps30).is_err()
        );
    }

    #[test]
    fn high_speed_modes_do_not_claim_native_sixty_fps() {
        let modes = parse_camera_modes(CAMERAS);
        assert_eq!(modes.len(), 2);
        assert_eq!(modes[0].sizes, vec!["1920x1080", "1280x720"]);
        assert_eq!(
            supported_fps(&modes, Facing::Back, FrameSize::Hd720),
            vec![FrameRate::Fps15, FrameRate::Fps30]
        );
        assert_eq!(
            supported_fps(&modes, Facing::Front, FrameSize::Fhd1080),
            vec![FrameRate::Fps15, FrameRate::Fps30, FrameRate::Fps60]
        );
        assert!(supported_fps(&modes, Facing::Front, FrameSize::Hd720).is_empty());
    }

    #[test]
    fn command_contains_camera_only_flags() {
        let args = camera_command(
            Path::new("C:/scrcpy/scrcpy.exe"),
            &request("abc123"),
            Platform::Windows,
        );
        assert_eq!(args[0], "C:/scrcpy/scrcpy.exe");
        for expected in [
            "--serial=abc123",
            "--video-source=camera",
            "--camera-facing=back",
            "--camera-size=1920x1080",
            "--camera-fps=30",
            "--no-audio",
        ] {
            assert!(
                args.iter().any(|argument| argument == expected),
                "{expected}"
            );
        }
    }

    #[test]
    fn windows_keeps_preview_window_open() {
        let args = camera_command(Path::new("scrcpy"), &request("abc"), Platform::Windows);
        assert!(!args.iter().any(|argument| argument == "--no-window"));
    }

    #[test]
    fn linux_without_sink_hides_the_window() {
        let args = camera_command(Path::new("scrcpy"), &request("abc"), Platform::Other);
        assert!(args.iter().any(|argument| argument == "--no-window"));
    }
}
