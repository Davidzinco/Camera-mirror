//! Process and error plumbing shared by the Android modules.

use std::fmt;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

pub type Result<T> = std::result::Result<T, AndroidError>;

/// Every error the user can be shown, with an actionable message.
#[derive(Debug, thiserror::Error)]
pub enum AndroidError {
    #[error("{0}")]
    Invalid(String),
    #[error("Program '{program}' belum terpasang atau tidak ditemukan di PATH. {hint}")]
    MissingProgram { program: String, hint: String },
    #[error("{0}")]
    CommandFailed(String),
    #[error("Perintah '{program}' melewati batas waktu {seconds} detik.")]
    Timeout { program: String, seconds: u64 },
    #[error(transparent)]
    Io(#[from] std::io::Error),
}

impl AndroidError {
    pub fn invalid(message: impl Into<String>) -> Self {
        Self::Invalid(message.into())
    }
}

/// Abstraction over process execution so the ADB layer is testable.
pub trait Runner: fmt::Debug {
    /// Run one command. `args[0]` is the program name or path.
    fn run(&self, args: &[String], input: Option<&str>, timeout: Duration) -> Result<String>;
}

/// Runs real child processes without a shell.
#[derive(Debug, Clone, Copy)]
pub struct ProcessRunner {
    /// Hide console windows for background queries (Windows only).
    pub hide_window: bool,
}

impl Default for ProcessRunner {
    fn default() -> Self {
        Self { hide_window: true }
    }
}

impl Runner for ProcessRunner {
    fn run(&self, args: &[String], input: Option<&str>, timeout: Duration) -> Result<String> {
        let Some((program, rest)) = args.split_first() else {
            return Err(AndroidError::invalid("Perintah kosong."));
        };
        let executable = find_executable(program);
        let mut command = Command::new(&executable);
        command
            .args(rest)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if self.hide_window {
            hide_console_window(&mut command);
        }

        let mut child = command.spawn().map_err(|error| {
            if error.kind() == std::io::ErrorKind::NotFound {
                AndroidError::MissingProgram {
                    program: program.clone(),
                    hint: install_hint(program),
                }
            } else {
                AndroidError::Io(error)
            }
        })?;

        if let Some(text) = input {
            if let Some(mut stdin) = child.stdin.take() {
                stdin.write_all(text.as_bytes())?;
            }
        } else {
            drop(child.stdin.take());
        }

        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        let stdout_reader = stdout.map(spawn_reader);
        let stderr_reader = stderr.map(spawn_reader);

        let deadline = Instant::now() + timeout;
        let status = loop {
            if let Some(status) = child.try_wait()? {
                break status;
            }
            if Instant::now() >= deadline {
                let _ = child.kill();
                let _ = child.wait();
                return Err(AndroidError::Timeout {
                    program: program.clone(),
                    seconds: timeout.as_secs(),
                });
            }
            std::thread::sleep(Duration::from_millis(20));
        };

        let mut output = String::new();
        if let Some(reader) = stdout_reader {
            output.push_str(&reader.join().unwrap_or_default());
        }
        if let Some(reader) = stderr_reader {
            output.push_str(&reader.join().unwrap_or_default());
        }
        let output = output.trim().to_owned();

        if status.success() {
            Ok(output)
        } else if output.is_empty() {
            Err(AndroidError::CommandFailed(format!(
                "Perintah gagal: {program}"
            )))
        } else {
            Err(AndroidError::CommandFailed(output))
        }
    }
}

/// Hide the console window of a child process.
///
/// `cfg!(windows)` only guards runtime branches, so the `std::os::windows`
/// import has to live behind a `#[cfg]` attribute to keep the crate building
/// (and lint-clean) on Linux and macOS.
#[cfg(windows)]
pub(crate) fn hide_console_window(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    command.creation_flags(CREATE_NO_WINDOW);
}

/// Hiding the console is a Windows-only concern; elsewhere this is a no-op.
#[cfg(not(windows))]
pub(crate) fn hide_console_window(_command: &mut Command) {}

fn spawn_reader(mut stream: impl Read + Send + 'static) -> std::thread::JoinHandle<String> {
    std::thread::spawn(move || {
        let mut buffer = Vec::new();
        let _ = stream.read_to_end(&mut buffer);
        String::from_utf8_lossy(&buffer).into_owned()
    })
}

/// Platform-specific hint shown when a required program is missing.
pub fn install_hint(program: &str) -> String {
    if cfg!(windows) {
        windows_install_hint(program)
    } else {
        "Pasang scrcpy & adb dari package manager distro Linux Anda.".into()
    }
}

/// Install hint used on Windows, split out so it can be tested anywhere.
fn windows_install_hint(program: &str) -> String {
    let name = Path::new(program)
        .file_stem()
        .and_then(|stem| stem.to_str())
        .unwrap_or(program)
        .to_ascii_lowercase();
    match name.as_str() {
        "adb" => "Pasang dengan: winget install Google.PlatformTools \
                  (paket scrcpy juga menyertakan adb)"
            .into(),
        "scrcpy" => "Pasang dengan: winget install Genymobile.scrcpy".into(),
        _ => "Pasang program tersebut lalu jalankan Camera Mirror lagi.".into(),
    }
}

/// Resolve a program through `PATH` and common Windows install locations.
pub fn find_executable(name: &str) -> PathBuf {
    let has_extension = Path::new(name).extension().is_some();
    let candidates = if cfg!(windows) && !has_extension {
        vec![format!("{name}.exe"), name.to_owned()]
    } else {
        vec![name.to_owned()]
    };

    if let Some(path) = std::env::var_os("PATH") {
        for folder in std::env::split_paths(&path) {
            for candidate in &candidates {
                let full = folder.join(candidate);
                if full.is_file() {
                    return full;
                }
            }
        }
    }

    if cfg!(windows) {
        for folder in windows_search_folders() {
            for candidate in &candidates {
                let full = folder.join(candidate);
                if full.is_file() {
                    return full;
                }
            }
        }
        // WinGet may extract a portable package without creating a shim.
        if let Some(packages) = env_path("LOCALAPPDATA")
            .map(|local| local.join("Microsoft").join("WinGet").join("Packages"))
        {
            for candidate in &candidates {
                if let Some(found) = search_tree(&packages, candidate, 6) {
                    return found;
                }
            }
        }
    }

    PathBuf::from(name)
}

/// Depth-limited search for a file name inside WinGet's package directory.
fn search_tree(root: &Path, file_name: &str, depth: u8) -> Option<PathBuf> {
    if depth == 0 {
        return None;
    }
    for entry in std::fs::read_dir(root).ok()?.flatten() {
        let path = entry.path();
        if path.is_file()
            && path
                .file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.eq_ignore_ascii_case(file_name))
        {
            return Some(path);
        }
        if path.is_dir() {
            if let Some(found) = search_tree(&path, file_name, depth - 1) {
                return Some(found);
            }
        }
    }
    None
}

fn windows_search_folders() -> Vec<PathBuf> {
    let local = env_path("LOCALAPPDATA");
    let profile = env_path("USERPROFILE");
    let programs = env_path("ProgramFiles");
    let mut folders = vec![
        PathBuf::from("C:/scrcpy"),
        PathBuf::from("C:/platform-tools"),
    ];
    if let Some(local) = &local {
        folders.push(local.join("Microsoft").join("WinGet").join("Links"));
        folders.push(local.join("Android").join("Sdk").join("platform-tools"));
        folders.push(local.join("Programs").join("scrcpy"));
    }
    if let Some(profile) = &profile {
        folders.push(profile.join("scrcpy"));
    }
    if let Some(programs) = &programs {
        folders.push(programs.join("scrcpy"));
    }
    folders
}

fn env_path(name: &str) -> Option<PathBuf> {
    std::env::var_os(name)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
}

/// Validate a literal `IP:port` endpoint (IPv6 must be bracketed).
pub fn endpoint(value: &str) -> Result<String> {
    let value = value.trim();
    let Some((host, port)) = value.rsplit_once(':') else {
        return Err(AndroidError::invalid(
            "Gunakan IP:port dari layar Wireless debugging, contoh 192.168.1.20:37123.",
        ));
    };
    let host = host.trim_start_matches('[').trim_end_matches(']');
    let port: u16 = port
        .parse()
        .map_err(|_| AndroidError::invalid("Port harus berupa angka 1 sampai 65535."))?;
    if port == 0 {
        return Err(AndroidError::invalid(
            "Port harus berupa angka 1 sampai 65535.",
        ));
    }
    if host.parse::<std::net::IpAddr>().is_err() {
        return Err(AndroidError::invalid(
            "Gunakan alamat IP, bukan nama host. Contoh: 192.168.1.20:37123.",
        ));
    }
    Ok(value.to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_invalid_network_endpoints() {
        for value in [
            "",
            "-x",
            "192.168.1.2",
            "192.168.1.2:0",
            "192.168.1.2:65536",
            "host;touch /tmp/file:5555",
        ] {
            assert!(endpoint(value).is_err(), "{value}");
        }
    }

    #[test]
    fn accepts_trimmed_and_bracketed_endpoints() {
        assert_eq!(
            endpoint(" 192.168.1.2:33333 ").unwrap(),
            "192.168.1.2:33333"
        );
        assert_eq!(endpoint("[fd00::1]:33333").unwrap(), "[fd00::1]:33333");
    }

    #[test]
    fn windows_hints_name_the_right_package() {
        assert!(windows_install_hint("adb").contains("Google.PlatformTools"));
        assert!(windows_install_hint("C:/tools/adb.exe").contains("Google.PlatformTools"));
        assert!(windows_install_hint("scrcpy").contains("Genymobile.scrcpy"));
        assert!(windows_install_hint("ffmpeg").contains("Camera Mirror lagi"));
    }
}
