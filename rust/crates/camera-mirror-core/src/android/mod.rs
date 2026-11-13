//! Android phone camera support built on ADB and scrcpy.

pub mod adb;
pub mod camera;
pub mod runner;
pub mod session;
pub mod wireless;

pub use adb::{DeviceInfo, DeviceMode};
pub use camera::{CameraRequest, Facing, FrameRate, FrameSize, Platform};
pub use runner::{AndroidError, ProcessRunner, Result, Runner};
pub use session::CameraSession;
pub use wireless::Service;
