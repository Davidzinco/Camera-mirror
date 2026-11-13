//! Showing the scrcpy preview inside the application window.
//!
//! scrcpy always opens a top-level window of its own. On Windows we reparent
//! that window into the eframe window so the picture appears inside the preview
//! box instead of in a separate window. Other platforms keep the native window
//! because scrcpy can write straight to a V4L2 device there.

/// Rectangle in physical pixels, relative to the host window's client area.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PhysicalRect {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

/// Raw window handle of the embedding host, as an opaque integer so the type
/// stays independent of `raw-window-handle` in the rest of the app.
pub type HostHandle = isize;

#[derive(Default)]
pub struct Preview {
    #[cfg(windows)]
    inner: windows::Embedded,
}

impl Preview {
    pub fn new() -> Self {
        Self::default()
    }

    /// Take over the scrcpy window owned by `pid`, if it exists yet.
    ///
    /// Safe to call every frame: it waits for the window, retries at most four
    /// times per second and does nothing once the window is embedded.
    pub fn attach(&mut self, host: HostHandle, pid: u32) {
        #[cfg(windows)]
        self.inner.attach(host, pid);
        #[cfg(not(windows))]
        {
            let _ = (host, pid);
        }
    }

    /// Move the embedded picture into `rect`, or hide it when `visible` is
    /// false.
    pub fn place(&mut self, rect: PhysicalRect, visible: bool) {
        #[cfg(windows)]
        self.inner.place(rect, visible);
        #[cfg(not(windows))]
        {
            let _ = (rect, visible);
        }
    }

    /// `true` once scrcpy's window lives inside the application window.
    pub fn is_embedded(&self) -> bool {
        #[cfg(windows)]
        {
            self.inner.is_embedded()
        }
        #[cfg(not(windows))]
        {
            false
        }
    }

    /// Forget the embedded window, e.g. after scrcpy was stopped.
    pub fn release(&mut self) {
        #[cfg(windows)]
        self.inner.release();
    }
}

#[cfg(windows)]
mod windows {
    use super::{HostHandle, PhysicalRect};
    use std::ffi::c_void;
    use std::ptr;
    use std::time::{Duration, Instant};

    type Hwnd = *mut c_void;
    type Bool = i32;

    const GWL_STYLE: i32 = -16;

    const WS_CHILD: isize = 0x4000_0000;
    const WS_POPUP: isize = 0x8000_0000;
    const WS_CAPTION: isize = 0x00c0_0000;
    const WS_THICKFRAME: isize = 0x0004_0000;
    const WS_MINIMIZEBOX: isize = 0x0002_0000;
    const WS_MAXIMIZEBOX: isize = 0x0001_0000;
    const WS_SYSMENU: isize = 0x0008_0000;

    const SWP_NOZORDER: u32 = 0x0004;
    const SWP_NOACTIVATE: u32 = 0x0010;
    const SWP_FRAMECHANGED: u32 = 0x0020;
    const SWP_SHOWWINDOW: u32 = 0x0040;

    const SW_HIDE: i32 = 0;

    #[link(name = "user32")]
    unsafe extern "system" {
        fn EnumWindows(callback: extern "system" fn(Hwnd, isize) -> Bool, lparam: isize) -> Bool;
        fn GetWindowThreadProcessId(hwnd: Hwnd, pid: *mut u32) -> u32;
        fn IsWindow(hwnd: Hwnd) -> Bool;
        fn IsWindowVisible(hwnd: Hwnd) -> Bool;
        fn GetParent(hwnd: Hwnd) -> Hwnd;
        fn SetParent(hwnd: Hwnd, parent: Hwnd) -> Hwnd;
        fn GetWindowLongW(hwnd: Hwnd, index: i32) -> i32;
        fn SetWindowLongW(hwnd: Hwnd, index: i32, value: i32) -> i32;
        fn SetWindowPos(
            hwnd: Hwnd,
            after: Hwnd,
            x: i32,
            y: i32,
            width: i32,
            height: i32,
            flags: u32,
        ) -> Bool;
        fn ShowWindow(hwnd: Hwnd, command: i32) -> Bool;
    }

    /// Minimum delay between searches for the scrcpy window.
    const SEARCH_INTERVAL: Duration = Duration::from_millis(250);

    #[derive(Default)]
    pub(super) struct Embedded {
        child: Option<Hwnd>,
        last_search: Option<Instant>,
        last_rect: Option<PhysicalRect>,
        visible: bool,
    }

    impl Embedded {
        pub(super) fn attach(&mut self, host: HostHandle, pid: u32) {
            if let Some(child) = self.child {
                if unsafe { IsWindow(child) } != 0 {
                    return;
                }
                // scrcpy was stopped and its window destroyed.
                self.child = None;
                self.last_rect = None;
                self.visible = false;
            }
            if host == 0 {
                return;
            }
            if self
                .last_search
                .is_some_and(|last| last.elapsed() < SEARCH_INTERVAL)
            {
                return;
            }
            self.last_search = Some(Instant::now());
            let Some(child) = find_window(pid) else {
                return;
            };
            embed(host as Hwnd, child);
            self.child = Some(child);
            self.last_rect = None;
            self.visible = false;
        }

        pub(super) fn place(&mut self, rect: PhysicalRect, visible: bool) {
            let Some(child) = self.child else {
                return;
            };
            if unsafe { IsWindow(child) } == 0 {
                self.child = None;
                self.last_rect = None;
                self.visible = false;
                return;
            }
            if !visible {
                if self.visible {
                    unsafe { ShowWindow(child, SW_HIDE) };
                    self.visible = false;
                }
                return;
            }
            if self.visible && self.last_rect == Some(rect) {
                return;
            }
            let mut flags = SWP_NOZORDER | SWP_NOACTIVATE;
            if !self.visible {
                flags |= SWP_SHOWWINDOW;
            }
            // SAFETY: `child` was checked with `IsWindow` above.
            unsafe {
                SetWindowPos(
                    child,
                    ptr::null_mut(),
                    rect.x,
                    rect.y,
                    rect.width.max(1),
                    rect.height.max(1),
                    flags,
                );
            }
            self.visible = true;
            self.last_rect = Some(rect);
        }

        pub(super) fn is_embedded(&self) -> bool {
            self.child.is_some()
        }

        pub(super) fn release(&mut self) {
            if let Some(child) = self.child.take() {
                // SAFETY: the handle was validated before it was stored.
                if unsafe { IsWindow(child) } != 0 {
                    unsafe {
                        ShowWindow(child, SW_HIDE);
                        SetParent(child, ptr::null_mut());
                    }
                }
            }
            self.last_rect = None;
            self.visible = false;
        }
    }

    /// Convert the top-level scrcpy window into a borderless child window.
    fn embed(host: Hwnd, child: Hwnd) {
        // SAFETY: both handles are valid windows owned by processes we can
        // address; the style bits are used only after being read back.
        unsafe {
            let style = GetWindowLongW(child, GWL_STYLE) as isize;
            let chrome = WS_POPUP
                | WS_CAPTION
                | WS_THICKFRAME
                | WS_MINIMIZEBOX
                | WS_MAXIMIZEBOX
                | WS_SYSMENU;
            SetWindowLongW(child, GWL_STYLE, ((style & !chrome) | WS_CHILD) as i32);
            SetParent(child, host);
            SetWindowPos(
                child,
                ptr::null_mut(),
                0,
                0,
                1,
                1,
                SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            );
            ShowWindow(child, SW_HIDE);
        }
    }

    struct Search {
        pid: u32,
        found: Option<Hwnd>,
    }

    /// Find the first visible top-level window owned by `pid`.
    fn find_window(pid: u32) -> Option<Hwnd> {
        extern "system" fn callback(hwnd: Hwnd, lparam: isize) -> Bool {
            // SAFETY: `lparam` points at a `Search` that outlives the call.
            let search = unsafe { &mut *(lparam as *mut Search) };
            let mut owner = 0u32;
            // SAFETY: `hwnd` comes from `EnumWindows` and is only queried.
            unsafe { GetWindowThreadProcessId(hwnd, &mut owner) };
            if owner != search.pid
                || unsafe { IsWindowVisible(hwnd) } == 0
                || !unsafe { GetParent(hwnd) }.is_null()
            {
                return 1;
            }
            search.found = Some(hwnd);
            0
        }

        let mut search = Search { pid, found: None };
        // SAFETY: the callback only touches `search`, which lives on this
        // stack frame for the duration of the enumeration.
        unsafe { EnumWindows(callback, &mut search as *mut Search as isize) };
        search.found
    }
}
