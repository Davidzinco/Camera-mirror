//! Transport-independent logic for Camera Mirror.
//!
//! The crate deliberately avoids GUI and async runtimes so that it can be
//! reused by the desktop app, the diagnostics CLI and future platform
//! backends. Everything that touches a process goes through [`android::Runner`]
//! so it can be replaced in tests.

pub mod android;
pub mod frames;
pub mod gate;
pub mod invitation;
pub mod preferences;

/// Application name used in window titles, shortcuts and dialogs.
pub const APP_NAME: &str = "Camera Mirror";

/// Crate version, taken from `Cargo.toml` at compile time.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
