//! Wireless setup and reconnection, restricted to devices the user enrolled.

use super::adb::{DeviceInfo, DeviceMode, connect};
use super::runner::{AndroidError, Result, Runner, endpoint, find_executable};
use crate::preferences::{Preferences, WirelessDevice};
use regex::Regex;
use std::net::Ipv4Addr;
use std::sync::OnceLock;
use std::time::Duration;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Service {
    pub name: String,
    pub address: String,
}

/// Read the hardware identity through ADB. Never trust an address alone.
pub fn identity(runner: &dyn Runner, address: &str) -> Result<String> {
    let mut last = String::new();
    for property in ["ro.serialno", "ro.boot.serialno"] {
        let value = runner.run(
            &[
                "adb".into(),
                "-s".into(),
                address.to_owned(),
                "shell".into(),
                "getprop".into(),
                property.into(),
            ],
            None,
            Duration::from_secs(5),
        );
        match value {
            Ok(value) => {
                let value = value.trim();
                if !value.is_empty() && !value.eq_ignore_ascii_case("unknown") {
                    return Ok(value.to_owned());
                }
                last = value.to_owned();
            }
            // Some ROMs reject one property; try the other before giving up.
            Err(error) => last = error.to_string(),
        }
    }
    Err(AndroidError::invalid(if last.is_empty() {
        "Identitas HP belum terbaca. Izinkan USB debugging di HP."
    } else {
        "Identitas HP tidak valid. Putuskan lalu sambungkan kembali kabel USB."
    }))
}

/// Connect, then verify that the address still belongs to the expected phone.
pub fn connect_checked(
    runner: &dyn Runner,
    address: &str,
    expected: Option<&str>,
) -> Result<String> {
    endpoint(address)?;
    runner.run(
        &["adb".into(), "connect".into(), address.to_owned()],
        None,
        Duration::from_secs(6),
    )?;
    let actual = identity(runner, address)?;
    if let Some(expected) = expected {
        if actual != expected {
            return Err(AndroidError::invalid(
                "Alamat jaringan ini bukan HP yang disimpan. Pilih Hubungkan HP lagi.",
            ));
        }
    }
    Ok(actual)
}

/// Switch a USB-connected phone to ADB over Wi-Fi and remember it.
pub fn setup_usb(
    runner: &dyn Runner,
    device: &DeviceInfo,
    preferences: &mut Preferences,
) -> Result<String> {
    if device.mode != DeviceMode::Usb {
        return Err(AndroidError::invalid(
            "Hubungkan kabel USB terlebih dahulu.",
        ));
    }
    let physical = identity(runner, &device.serial)?;
    let host = wifi_address(runner, &device.serial).ok_or_else(|| {
        AndroidError::invalid("Sambungkan HP ke Wi-Fi yang sama dengan komputer, lalu coba lagi.")
    })?;
    let address = format!("{host}:5555");
    runner.run(
        &[
            "adb".into(),
            "-s".into(),
            device.serial.clone(),
            "tcpip".into(),
            "5555".into(),
        ],
        None,
        Duration::from_secs(10),
    )?;

    // adbd restarts after `tcpip`, so the first attempts often fail while the
    // phone is still switching transports. Keep retrying for about ten seconds.
    let mut last_error = None;
    for attempt in 1..=10 {
        std::thread::sleep(Duration::from_millis(if attempt == 1 { 1200 } else { 800 }));
        match connect_checked(runner, &address, Some(&physical)) {
            Ok(_) => {
                preferences.remember(WirelessDevice {
                    serial: physical,
                    address: address.clone(),
                    name: device.name.clone(),
                    service: String::new(),
                });
                return Ok(address);
            }
            Err(error) => last_error = Some(error),
        }
    }
    Err(AndroidError::CommandFailed(format!(
        "Belum bisa terhubung lewat Wi-Fi ({address}). Pastikan HP dan komputer berada di jaringan yang sama.\n{}",
        last_error
            .map(|error| error.to_string())
            .unwrap_or_else(|| "Percobaan koneksi habis.".into())
    )))
}

/// LAN address of the phone, preferring `wlan0` but falling back to any
/// non-loopback IPv4 interface.
fn wifi_address(runner: &dyn Runner, serial: &str) -> Option<Ipv4Addr> {
    let wlan = runner.run(
        &[
            "adb".into(),
            "-s".into(),
            serial.to_owned(),
            "shell".into(),
            "ip".into(),
            "-o".into(),
            "-4".into(),
            "addr".into(),
            "show".into(),
            "wlan0".into(),
        ],
        None,
        Duration::from_secs(10),
    );
    if let Ok(output) = wlan
        && let Some(address) = first_routable_ipv4(&output)
    {
        return Some(address);
    }
    let all = runner
        .run(
            &[
                "adb".into(),
                "-s".into(),
                serial.to_owned(),
                "shell".into(),
                "ip".into(),
                "-o".into(),
                "-4".into(),
                "addr".into(),
                "show".into(),
            ],
            None,
            Duration::from_secs(10),
        )
        .ok()?;
    first_routable_ipv4(&all)
}

fn first_routable_ipv4(output: &str) -> Option<Ipv4Addr> {
    output.lines().find_map(|line| {
        let address = ipv4_pattern()
            .captures(line)
            .and_then(|captures| captures[1].parse::<Ipv4Addr>().ok())?;
        (!address.is_loopback() && !address.is_link_local()).then_some(address)
    })
}

/// Reconnect to the first enrolled phone that is reachable, verifying identity.
///
/// The `connect` callback receives `(address, expected_serial)`.
pub fn reconnect<F>(
    preferences: &Preferences,
    connected: &[DeviceInfo],
    mut connect: F,
) -> Option<String>
where
    F: FnMut(&str, &str) -> Result<String>,
{
    if !preferences.auto_connect {
        return None;
    }
    for device in &preferences.wireless {
        if device.address.is_empty() || device.serial.is_empty() {
            continue;
        }
        if connected.iter().any(|item| item.serial == device.address) {
            return Some(device.address.clone());
        }
        if connect(&device.address, &device.serial).is_ok() {
            return Some(device.address.clone());
        }
    }
    None
}

fn ipv4_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"\binet\s+(\d+\.\d+\.\d+\.\d+)/").expect("inet pattern is valid")
    })
}

/// Parse resolved `avahi-browse -rtp` records.
pub fn parse_services(output: &str, kind: &str) -> Vec<Service> {
    let mut services: Vec<Service> = Vec::new();
    for line in output.lines() {
        let parts: Vec<&str> = line.split(';').collect();
        if parts.len() < 9 || parts[0] != "=" || parts[4] != kind {
            continue;
        }
        let Ok(host) = parts[7].parse::<Ipv4Addr>() else {
            continue;
        };
        let Ok(address) = endpoint(&format!("{host}:{}", parts[8])) else {
            continue;
        };
        let service = Service {
            name: parts[3].to_owned(),
            address,
        };
        if !services.contains(&service) {
            services.push(service);
        }
    }
    services
}

/// mDNS discovery through Avahi when it is installed (Linux).
pub fn discover(runner: &dyn Runner, kind: &str) -> Vec<Service> {
    if !cfg!(target_os = "linux") {
        return Vec::new();
    }
    let executable = find_executable("avahi-browse");
    if !executable.is_file() {
        return Vec::new();
    }
    let output = runner.run(
        &[
            executable.display().to_string(),
            "-rtp".into(),
            kind.to_owned(),
        ],
        None,
        Duration::from_secs(4),
    );
    match output {
        Ok(text) => parse_services(&text, kind),
        Err(_) => Vec::new(),
    }
}

/// Use `connect` directly for callers that already have a runner.
pub fn connect_address(runner: &dyn Runner, address: &str) -> Result<String> {
    connect(runner, address)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    #[test]
    fn discovery_uses_resolved_services_only() {
        let output = "+;wlan0;IPv4;adb-PHONE-a;_adb-tls-connect._tcp;local\n\
            =;wlan0;IPv4;adb-PHONE-a;_adb-tls-connect._tcp;local;phone.local;192.168.1.20;38000;\n\
            =;wlan0;IPv4;printer;_ipp._tcp;local;printer.local;192.168.1.30;631;\n";
        assert_eq!(
            parse_services(output, "_adb-tls-connect._tcp"),
            vec![Service {
                name: "adb-PHONE-a".into(),
                address: "192.168.1.20:38000".into(),
            }]
        );
    }

    #[test]
    fn wifi_address_prefers_a_routable_interface() {
        let output = "1: lo    inet 127.0.0.1/8 scope host lo\n\
                      2: wlan0    inet 192.168.1.5/24 brd 192.168.1.255 scope global wlan0\n";
        assert_eq!(
            first_routable_ipv4(output),
            Some("192.168.1.5".parse().unwrap())
        );
    }

    #[test]
    fn wifi_address_skips_loopback_and_link_local() {
        let output = "1: lo    inet 127.0.0.1/8 scope host lo\n\
                      2: rmnet0    inet 169.254.10.2/16 scope link rmnet0\n";
        assert_eq!(first_routable_ipv4(output), None);
    }

    #[derive(Debug, Default)]
    struct FakeRunner {
        calls: Cell<usize>,
        first: bool,
    }

    impl Runner for FakeRunner {
        fn run(
            &self,
            _args: &[String],
            _input: Option<&str>,
            _timeout: Duration,
        ) -> Result<String> {
            let call = self.calls.get();
            self.calls.set(call + 1);
            if call == 0 && self.first {
                Err(AndroidError::CommandFailed("unknown property".into()))
            } else {
                Ok("RRCYA016B5A\n".into())
            }
        }
    }

    #[test]
    fn identity_falls_back_to_the_boot_serial() {
        let runner = FakeRunner {
            first: true,
            ..FakeRunner::default()
        };
        assert_eq!(
            identity(&runner, "192.168.1.20:5555").unwrap(),
            "RRCYA016B5A"
        );
        assert_eq!(runner.calls.get(), 2);
    }

    #[test]
    fn identity_reads_the_primary_serial_first() {
        let runner = FakeRunner::default();
        assert_eq!(
            identity(&runner, "192.168.1.20:5555").unwrap(),
            "RRCYA016B5A"
        );
        assert_eq!(runner.calls.get(), 1);
    }

    #[test]
    fn auto_connect_can_be_disabled() {
        let preferences = Preferences {
            auto_connect: false,
            ..Preferences::default()
        };
        let called = Cell::new(0);
        let result = reconnect(&preferences, &[], |_, _| {
            called.set(called.get() + 1);
            Err(AndroidError::invalid("must not run"))
        });
        assert!(result.is_none());
        assert_eq!(called.get(), 0);
    }

    #[test]
    fn reconnect_checks_saved_hardware_identity() {
        let preferences = Preferences {
            wireless: vec![WirelessDevice {
                serial: "MY-PHONE".into(),
                address: "192.168.1.20:5555".into(),
                name: "Phone".into(),
                service: String::new(),
            }],
            ..Preferences::default()
        };
        let calls = Cell::new(0);
        let result = reconnect(&preferences, &[], |address, expected| {
            calls.set(calls.get() + 1);
            assert_eq!(address, "192.168.1.20:5555");
            assert_eq!(expected, "MY-PHONE");
            Ok(expected.to_owned())
        });
        assert_eq!(result.as_deref(), Some("192.168.1.20:5555"));
        assert_eq!(calls.get(), 1);
    }

    #[test]
    fn reconnect_reuses_an_already_connected_address() {
        let preferences = Preferences {
            wireless: vec![WirelessDevice {
                serial: "MY-PHONE".into(),
                address: "192.168.1.20:5555".into(),
                name: "Phone".into(),
                service: String::new(),
            }],
            ..Preferences::default()
        };
        let connected = vec![DeviceInfo {
            serial: "192.168.1.20:5555".into(),
            name: "Phone".into(),
            mode: DeviceMode::Wifi,
            authorized: true,
        }];
        let result = reconnect(&preferences, &connected, |_, _| {
            Err(AndroidError::invalid("must not run"))
        });
        assert_eq!(result.as_deref(), Some("192.168.1.20:5555"));
    }
}
