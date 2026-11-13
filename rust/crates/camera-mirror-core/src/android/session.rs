//! Owning the long-running scrcpy process and its log buffer.

use super::camera::{CameraRequest, Platform, camera_command};
use super::runner::{AndroidError, Result, find_executable};
use std::collections::VecDeque;
use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

const MAX_LOG_LINES: usize = 100;

/// A single camera stream process. All methods are safe to call from the UI
/// thread; child output is drained on background threads.
#[derive(Debug, Default)]
pub struct CameraSession {
    child: Mutex<Option<Child>>,
    logs: Arc<Mutex<VecDeque<String>>>,
}

impl CameraSession {
    pub fn new() -> Self {
        Self::default()
    }

    /// Stop any previous stream and spawn scrcpy for `request`.
    pub fn start(&self, request: &CameraRequest, platform: Platform) -> Result<()> {
        self.stop();
        let scrcpy = find_executable("scrcpy");
        if !scrcpy.is_file() {
            return Err(AndroidError::MissingProgram {
                program: "scrcpy".into(),
                hint: super::runner::install_hint("scrcpy"),
            });
        }
        let args = camera_command(&scrcpy, request, platform);
        self.push_log(format!(
            "Menjalankan {} untuk kamera {} {}.",
            args[0],
            request.facing.as_str(),
            request.size.as_str()
        ));
        let mut command = Command::new(&args[0]);
        command
            .args(&args[1..])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if cfg!(windows) {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            // scrcpy still draws its own preview window; only the console is hidden.
            command.creation_flags(CREATE_NO_WINDOW);
        }
        let mut child = command.spawn().map_err(|error| {
            if error.kind() == std::io::ErrorKind::NotFound {
                AndroidError::MissingProgram {
                    program: "scrcpy".into(),
                    hint: super::runner::install_hint("scrcpy"),
                }
            } else {
                AndroidError::Io(error)
            }
        })?;
        if let Some(stdout) = child.stdout.take() {
            self.drain(stdout);
        }
        if let Some(stderr) = child.stderr.take() {
            self.drain(stderr);
        }
        *self.child.lock().unwrap_or_else(|error| error.into_inner()) = Some(child);
        Ok(())
    }

    fn drain(&self, stream: impl std::io::Read + Send + 'static) {
        let logs = Arc::clone(&self.logs);
        std::thread::spawn(move || {
            let mut reader = BufReader::new(stream);
            let mut line = String::new();
            while reader.read_line(&mut line).unwrap_or(0) > 0 {
                let trimmed = line.trim_end();
                if !trimmed.is_empty() {
                    push_bounded(&logs, trimmed.to_owned());
                }
                line.clear();
            }
        });
    }

    /// Terminate the current process, if any.
    pub fn stop(&self) {
        let child = self
            .child
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .take();
        if let Some(mut child) = child {
            let _ = child.kill();
            let _ = child.wait();
            self.push_log("Kamera dihentikan.");
        }
    }

    /// `true` while scrcpy is still running.
    pub fn active(&self) -> bool {
        let mut guard = self.child.lock().unwrap_or_else(|error| error.into_inner());
        let Some(child) = guard.as_mut() else {
            return false;
        };
        match child.try_wait() {
            Ok(Some(_)) => {
                *guard = None;
                false
            }
            Ok(None) => true,
            Err(_) => false,
        }
    }

    /// Process id of the running scrcpy, used to embed its preview window.
    pub fn child_pid(&self) -> Option<u32> {
        let mut guard = self.child.lock().unwrap_or_else(|error| error.into_inner());
        let status = guard.as_mut()?.try_wait();
        match status {
            Ok(None) => guard.as_ref().map(|child| child.id()),
            Ok(Some(_)) => {
                *guard = None;
                None
            }
            Err(_) => None,
        }
    }

    pub fn logs(&self) -> String {
        self.logs
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .iter()
            .cloned()
            .collect::<Vec<_>>()
            .join("\n")
    }

    pub fn push_log(&self, line: impl Into<String>) {
        push_bounded(&self.logs, line.into());
    }
}

fn push_bounded(logs: &Arc<Mutex<VecDeque<String>>>, line: String) {
    let mut logs = logs.lock().unwrap_or_else(|error| error.into_inner());
    if logs.len() >= MAX_LOG_LINES {
        logs.pop_front();
    }
    logs.push_back(line);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn logs_are_bounded() {
        let session = CameraSession::new();
        for index in 0..150 {
            session.push_log(format!("line {index}"));
        }
        let logs = session.logs();
        let lines: Vec<&str> = logs.lines().collect();
        assert_eq!(lines.len(), MAX_LOG_LINES);
        assert_eq!(lines.last(), Some(&"line 149"));
        assert_eq!(lines.first(), Some(&"line 50"));
    }

    #[test]
    fn idle_session_is_inactive_and_stoppable() {
        let session = CameraSession::new();
        assert!(!session.active());
        session.stop();
        assert!(!session.active());
    }
}
