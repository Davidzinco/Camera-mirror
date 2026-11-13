//! A bounded handoff between camera, network, virtual device and UI threads.
//!
//! Only the newest value is kept. Producers never block and slow consumers
//! cannot build up an unbounded frame backlog.

use std::sync::Mutex;
use std::time::{Duration, Instant};

#[derive(Debug)]
struct State<T> {
    value: Option<T>,
    sequence: u64,
    stamp: Option<Instant>,
}

/// Snapshot returned by [`LatestFrame::get`].
#[derive(Debug, Clone)]
pub struct FrameSnapshot<T> {
    pub value: Option<T>,
    pub sequence: u64,
    pub stamp: Option<Instant>,
}

impl<T> FrameSnapshot<T> {
    /// `true` when the newest value is older than `max_age`.
    pub fn is_stale(&self, max_age: Duration) -> bool {
        match self.stamp {
            Some(stamp) => stamp.elapsed() > max_age,
            None => true,
        }
    }

    /// `true` when a current value is available.
    pub fn is_fresh(&self, max_age: Duration) -> bool {
        self.value.is_some() && !self.is_stale(max_age)
    }
}

/// A thread-safe, single-slot mailbox that always keeps the latest value.
#[derive(Debug)]
pub struct LatestFrame<T> {
    state: Mutex<State<T>>,
}

impl<T> Default for LatestFrame<T> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T> LatestFrame<T> {
    pub fn new() -> Self {
        Self {
            state: Mutex::new(State {
                value: None,
                sequence: 0,
                stamp: None,
            }),
        }
    }

    /// Replace the stored value and return the new sequence number.
    pub fn put(&self, value: T) -> u64 {
        let mut state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        state.value = Some(value);
        state.sequence += 1;
        state.stamp = Some(Instant::now());
        state.sequence
    }

    /// Remove the stored value without resetting the sequence counter.
    pub fn clear(&self) {
        let mut state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        state.value = None;
        state.stamp = None;
    }

    /// Read the newest value. The `T` is cloned so callers never hold the lock.
    pub fn get(&self) -> FrameSnapshot<T>
    where
        T: Clone,
    {
        let state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        FrameSnapshot {
            value: state.value.clone(),
            sequence: state.sequence,
            stamp: state.stamp,
        }
    }

    /// Current sequence number, even when the value has been cleared.
    pub fn sequence(&self) -> u64 {
        self.state
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .sequence
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backlog_is_replaced() {
        let frames = LatestFrame::new();
        for value in 0..1000 {
            frames.put(value);
        }
        let snapshot = frames.get();
        assert_eq!((snapshot.value, snapshot.sequence), (Some(999), 1000));
        assert!(snapshot.stamp.is_some());
        assert!(!snapshot.is_stale(Duration::from_secs(1)));
    }

    #[test]
    fn clear_removes_stale_frame() {
        let frames = LatestFrame::new();
        frames.put("frame");
        frames.clear();
        let snapshot = frames.get();
        assert!(snapshot.value.is_none());
        assert!(snapshot.stamp.is_none());
        assert!(snapshot.is_stale(Duration::ZERO));
        assert_eq!(frames.sequence(), 1);
    }
}
