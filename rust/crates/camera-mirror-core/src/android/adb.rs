//! ADB device discovery and pairing.

use super::runner::{AndroidError, Result, Runner, endpoint};
use serde::{Deserialize, Serialize};
use std::time::Duration;

pub const QUERY_TIMEOUT: Duration = Duration::from_secs(25);
pub const PAIR_TIMEOUT: Duration = Duration::from_secs(60);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum DeviceMode {
    Usb,
    Wifi,
}

impl DeviceMode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Usb => "usb",
            Self::Wifi => "wifi",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DeviceInfo {
    pub serial: String,
    pub name: String,
    pub mode: DeviceMode,
    pub authorized: bool,
}

/// Parse `adb devices -l`, keeping only fully authorized devices.
pub fn parse_devices(output: &str) -> Vec<String> {
    output
        .lines()
        .filter_map(|line| {
            let mut fields = line.split_whitespace();
            let serial = fields.next()?;
            let state = fields.next()?;
            (state == "device").then(|| serial.to_owned())
        })
        .collect()
}

/// Parse `adb devices -l` into displayable devices, including unauthorized ones.
pub fn parse_device_details(output: &str) -> Vec<DeviceInfo> {
    output
        .lines()
        .filter_map(|line| {
            let fields: Vec<&str> = line.split_whitespace().collect();
            if fields.len() < 2 {
                return None;
            }
            let state = fields[1];
            if state != "device" && state != "unauthorized" {
                return None;
            }
            let model = fields
                .iter()
                .find_map(|field| field.strip_prefix("model:"))
                .map(|value| value.replace('_', " "))
                .unwrap_or_else(|| "HP Android".to_owned());
            let mode = if fields[0].contains(':') {
                DeviceMode::Wifi
            } else {
                DeviceMode::Usb
            };
            Some(DeviceInfo {
                serial: fields[0].to_owned(),
                name: model,
                mode,
                authorized: state == "device",
            })
        })
        .collect()
}

pub fn devices(runner: &dyn Runner) -> Result<Vec<String>> {
    let output = runner.run(
        &["adb".into(), "devices".into(), "-l".into()],
        None,
        QUERY_TIMEOUT,
    )?;
    Ok(parse_devices(&output))
}

pub fn device_details(runner: &dyn Runner) -> Vec<DeviceInfo> {
    match runner.run(
        &["adb".into(), "devices".into(), "-l".into()],
        None,
        Duration::from_secs(15),
    ) {
        Ok(output) => parse_device_details(&output),
        Err(_) => Vec::new(),
    }
}

/// Pair over wireless debugging. The six-digit code is sent on stdin so it
/// never appears in process arguments or logs.
pub fn pair(runner: &dyn Runner, address: &str, code: &str) -> Result<String> {
    let address = endpoint(address)?;
    if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(AndroidError::invalid("Kode pairing harus 6 angka."));
    }
    let input = format!("{code}\n");
    let output = runner.run(
        &["adb".into(), "pair".into(), address],
        Some(&input),
        PAIR_TIMEOUT,
    )?;
    if !output.to_ascii_lowercase().contains("successfully paired") {
        return Err(AndroidError::CommandFailed(output));
    }
    Ok("Pairing berhasil. Isi alamat koneksi dari halaman utama Wireless debugging.".into())
}

pub fn connect(runner: &dyn Runner, address: &str) -> Result<String> {
    let address = endpoint(address)?;
    let output = runner.run(
        &["adb".into(), "connect".into(), address.clone()],
        None,
        QUERY_TIMEOUT,
    )?;
    if !devices(runner)?.iter().any(|serial| serial == &address) {
        return Err(AndroidError::CommandFailed(format!(
            "{output}\nHP belum terhubung; cek IP, port, dan jaringan."
        )));
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    #[derive(Debug)]
    struct MockRunner {
        output: String,
        calls: RefCell<Vec<Vec<String>>>,
        inputs: RefCell<Vec<Option<String>>>,
    }

    impl MockRunner {
        fn new(output: &str) -> Self {
            Self {
                output: output.into(),
                calls: RefCell::new(Vec::new()),
                inputs: RefCell::new(Vec::new()),
            }
        }
    }

    impl Runner for MockRunner {
        fn run(&self, args: &[String], input: Option<&str>, _timeout: Duration) -> Result<String> {
            self.calls.borrow_mut().push(args.to_vec());
            self.inputs.borrow_mut().push(input.map(str::to_owned));
            Ok(self.output.clone())
        }
    }

    #[test]
    fn only_authorized_devices_are_listed() {
        let output = "List of devices attached\nabc unauthorized\ndef offline\nghi device usb:1\n192.168.1.2:5555 device\n";
        assert_eq!(parse_devices(output), vec!["ghi", "192.168.1.2:5555"]);
    }

    #[test]
    fn device_details_include_model_and_transport() {
        let output = "List of devices attached\n\
            abc unauthorized model:SM_A566B usb:1\n\
            ghi device model:SM_A566B usb:1\n\
            192.168.1.2:5555 device model:Pixel_7\n";
        let devices = parse_device_details(output);
        assert_eq!(devices.len(), 3);
        assert_eq!(devices[0].name, "SM A566B");
        assert!(!devices[0].authorized);
        assert_eq!(devices[1].mode, DeviceMode::Usb);
        assert!(devices[1].authorized);
        assert_eq!(devices[2].mode, DeviceMode::Wifi);
    }

    #[test]
    fn usb_devices_without_a_transport_field_are_still_usb() {
        // Windows adb does not always print `usb:`; the serial is the reliable
        // signal. Network serials always carry an `IP:port`.
        let output = "List of devices attached\n\
            RRCYA016B5A device model:SM_A566B transport_id:1\n\
            192.168.1.5:5555 device model:SM_A566B transport_id:2\n";
        let devices = parse_device_details(output);
        assert_eq!(devices[0].mode, DeviceMode::Usb);
        assert_eq!(devices[1].mode, DeviceMode::Wifi);
    }

    #[test]
    fn pairing_secret_is_not_in_arguments() {
        let runner = MockRunner::new("Successfully paired to 192.168.1.2:33333");
        pair(&runner, "192.168.1.2:33333", "123456").unwrap();
        let calls = runner.calls.borrow();
        assert!(!calls[0].iter().any(|argument| argument.contains("123456")));
        assert_eq!(runner.inputs.borrow()[0].as_deref(), Some("123456\n"));
    }

    #[test]
    fn adb_success_exit_with_failed_connection_is_rejected() {
        // `connect` needs a second call for `devices`; a sequential mock keeps
        // returning the same output, so the address is never listed.
        let runner = MockRunner::new("failed to connect");
        assert!(connect(&runner, "192.168.1.2:5555").is_err());
    }

    #[test]
    fn command_failure_preserves_diagnostic() {
        let error = AndroidError::CommandFailed("Device unavailable".into());
        assert!(error.to_string().contains("Device unavailable"));
    }
}
