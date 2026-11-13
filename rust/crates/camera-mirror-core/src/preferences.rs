//! Small, atomic user preferences. Pairing secrets never enter this file.

use serde::{Deserialize, Serialize};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

pub const MAX_REMEMBERED_DEVICES: usize = 8;

/// A phone that was enrolled for automatic reconnection.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct WirelessDevice {
    #[serde(default)]
    pub serial: String,
    #[serde(default)]
    pub address: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub service: String,
}

/// Everything Camera Mirror remembers between runs.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Preferences {
    pub mode: String,
    pub facing: String,
    pub size: String,
    pub fps: String,
    pub auto_connect: bool,
    pub wireless: Vec<WirelessDevice>,
    pub last_device: String,
    pub screen_off: bool,
    pub theme: String,
}

impl Default for Preferences {
    fn default() -> Self {
        Self {
            mode: "usb".into(),
            facing: "back".into(),
            size: "1920x1080".into(),
            fps: "30".into(),
            auto_connect: true,
            wireless: Vec::new(),
            last_device: String::new(),
            screen_off: false,
            theme: "dark".into(),
        }
    }
}

impl Preferences {
    /// `%APPDATA%\camera-mirror\preferences.json` on Windows and
    /// `$XDG_CONFIG_HOME/camera-mirror/preferences.json` elsewhere.
    pub fn path() -> PathBuf {
        config_root().join("camera-mirror").join("preferences.json")
    }

    /// Load from the platform path. A missing or corrupt file yields defaults.
    pub fn load() -> Self {
        Self::load_from(&Self::path())
    }

    pub fn load_from(path: &Path) -> Self {
        let Ok(text) = fs::read_to_string(path) else {
            return Self::default();
        };
        serde_json::from_str(&text).unwrap_or_default()
    }

    /// Persist atomically so a crash never leaves a half-written file.
    pub fn save(&self) -> io::Result<()> {
        self.save_to(&Self::path())
    }

    pub fn save_to(&self, path: &Path) -> io::Result<()> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
            restrict_directory(parent)?;
        }
        let temporary = path.with_extension("tmp");
        let json = serde_json::to_vec_pretty(self).map_err(io::Error::other)?;
        fs::write(&temporary, json)?;
        restrict_file(&temporary)?;
        fs::rename(&temporary, path)?;
        Ok(())
    }

    /// Store or update one enrolled phone, keeping the most recent eight.
    pub fn remember(&mut self, device: WirelessDevice) {
        self.wireless.retain(|item| item.serial != device.serial);
        self.wireless.push(device);
        if self.wireless.len() > MAX_REMEMBERED_DEVICES {
            let excess = self.wireless.len() - MAX_REMEMBERED_DEVICES;
            self.wireless.drain(0..excess);
        }
    }
}

fn config_root() -> PathBuf {
    if let Some(root) = env_path("XDG_CONFIG_HOME") {
        return root;
    }
    if cfg!(windows) {
        if let Some(app_data) = env_path("APPDATA") {
            return app_data;
        }
    }
    env_path("HOME")
        .or_else(|| env_path("USERPROFILE"))
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".config")
}

fn env_path(name: &str) -> Option<PathBuf> {
    std::env::var_os(name)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
}

#[cfg(unix)]
fn restrict_file(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))
}

#[cfg(not(unix))]
fn restrict_file(_path: &Path) -> io::Result<()> {
    Ok(())
}

#[cfg(unix)]
fn restrict_directory(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))
}

#[cfg(not(unix))]
fn restrict_directory(_path: &Path) -> io::Result<()> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU32, Ordering};

    static COUNTER: AtomicU32 = AtomicU32::new(0);

    fn temporary_path() -> PathBuf {
        let unique = COUNTER.fetch_add(1, Ordering::Relaxed);
        std::env::temp_dir().join(format!(
            "camera-mirror-test-{}-{unique}.json",
            std::process::id()
        ))
    }

    #[test]
    fn remember_preserves_settings_and_updates_address() {
        let path = temporary_path();
        let mut preferences = Preferences {
            facing: "front".into(),
            mode: "wifi".into(),
            ..Preferences::default()
        };
        preferences.remember(WirelessDevice {
            serial: "MY-PHONE".into(),
            address: "192.168.1.20:5555".into(),
            name: "Phone".into(),
            service: String::new(),
        });
        preferences.remember(WirelessDevice {
            serial: "MY-PHONE".into(),
            address: "192.168.1.21:5555".into(),
            name: "Phone".into(),
            service: String::new(),
        });
        preferences.save_to(&path).unwrap();

        let loaded = Preferences::load_from(&path);
        assert_eq!(loaded.facing, "front");
        assert_eq!(loaded.mode, "wifi");
        assert_eq!(loaded.wireless.len(), 1);
        assert_eq!(loaded.wireless[0].address, "192.168.1.21:5555");
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn corrupt_file_falls_back_to_defaults() {
        let path = temporary_path();
        fs::write(&path, "{not json").unwrap();
        assert_eq!(Preferences::load_from(&path), Preferences::default());
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn remembers_at_most_eight_devices() {
        let mut preferences = Preferences::default();
        for index in 0..12 {
            preferences.remember(WirelessDevice {
                serial: format!("PHONE-{index}"),
                address: format!("192.168.1.{index}:5555"),
                name: "Phone".into(),
                service: String::new(),
            });
        }
        assert_eq!(preferences.wireless.len(), MAX_REMEMBERED_DEVICES);
        assert_eq!(preferences.wireless.last().unwrap().serial, "PHONE-11");
    }
}
