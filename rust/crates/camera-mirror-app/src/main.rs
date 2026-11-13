//! Camera Mirror desktop application.
//!
//! Milestone 1 ports the Android phone-camera mode to Rust: ADB discovery,
//! wireless pairing and a managed scrcpy process. The LAN WebRTC mode is
//! still served by the Python implementation while the media pipeline is
//! ported in milestone 2; the UI says so explicitly instead of pretending
//! otherwise.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod app;
mod preview;
mod theme;

use camera_mirror_core::APP_NAME;

/// Backends to offer wgpu on Windows.
///
/// Some Intel Vulkan drivers (`igvk64.dll`) crash with an access violation
/// while wgpu enumerates adapters, so Vulkan is dropped unless the user asks
/// for it explicitly through `WGPU_BACKEND`.
#[cfg(target_os = "windows")]
fn windows_backends(requested: Option<eframe::wgpu::Backends>) -> eframe::wgpu::Backends {
    let mut backends =
        requested.unwrap_or(eframe::wgpu::Backends::PRIMARY | eframe::wgpu::Backends::GL);
    if requested.is_none() {
        backends.remove(eframe::wgpu::Backends::VULKAN);
    }
    backends
}

fn main() -> eframe::Result<()> {
    let mut options = eframe::NativeOptions {
        viewport: eframe::egui::ViewportBuilder::default()
            .with_inner_size([1040.0, 700.0])
            .with_min_inner_size([760.0, 560.0])
            .with_title(APP_NAME),
        ..Default::default()
    };
    #[cfg(target_os = "windows")]
    {
        if let eframe::egui_wgpu::WgpuSetup::CreateNew(setup) = &mut options.wgpu_options.wgpu_setup
        {
            setup.instance_descriptor.backends =
                windows_backends(eframe::wgpu::Backends::from_env());
        }
    }
    eframe::run_native(
        APP_NAME,
        options,
        Box::new(|creation_context| Ok(Box::new(app::CameraMirrorApp::new(creation_context)))),
    )
}

#[cfg(all(test, target_os = "windows"))]
mod tests {
    use super::windows_backends;
    use eframe::wgpu::Backends;

    #[test]
    fn windows_avoids_vulkan_by_default() {
        let backends = windows_backends(None);
        assert!(backends.contains(Backends::DX12));
        assert!(!backends.contains(Backends::VULKAN));
    }

    #[test]
    fn explicit_backend_request_is_kept() {
        assert_eq!(windows_backends(Some(Backends::VULKAN)), Backends::VULKAN);
    }
}
