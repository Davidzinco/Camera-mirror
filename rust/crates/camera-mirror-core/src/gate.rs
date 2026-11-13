//! One-receiver pairing gate with monotonic expiry and bounded attempts.

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use std::time::{SystemTime, UNIX_EPOCH};

/// Seconds since the Unix epoch; injectable so tests do not sleep.
pub type Clock = fn() -> f64;

fn system_clock() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs_f64())
        .unwrap_or(0.0)
}

/// Generate a 43-character URL-safe token from 32 random bytes.
pub fn random_token() -> String {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).expect("operating system random source is available");
    URL_SAFE_NO_PAD.encode(bytes)
}

/// Claims a single invitation exactly once.
#[derive(Debug)]
pub struct PairingGate<C: Fn() -> f64 = Clock> {
    pub token: String,
    pub deadline: f64,
    pub attempts: u32,
    pub used: bool,
    clock: C,
}

impl PairingGate<Clock> {
    /// A gate using the system clock and a random token.
    pub fn new(ttl_secs: f64, attempts: u32) -> Self {
        Self::with_clock(ttl_secs, attempts, system_clock)
    }
}

impl<C: Fn() -> f64> PairingGate<C> {
    pub fn with_clock(ttl_secs: f64, attempts: u32, clock: C) -> Self {
        Self {
            token: random_token(),
            deadline: clock() + ttl_secs,
            attempts,
            used: false,
            clock,
        }
    }

    /// Claim the invitation. A wrong token consumes one attempt.
    pub fn claim(&mut self, token: &str) -> bool {
        if self.used || (self.clock)() >= self.deadline || self.attempts == 0 {
            return false;
        }
        if !constant_time_eq(token.as_bytes(), self.token.as_bytes()) {
            self.attempts -= 1;
            return false;
        }
        self.used = true;
        true
    }
}

/// Compare without early exit so a wrong token cannot be discovered byte by byte.
fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    let mut difference = 0u8;
    for (a, b) in left.iter().zip(right) {
        difference |= a ^ b;
    }
    difference == 0
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::rc::Rc;

    #[test]
    fn token_shape() {
        let token = random_token();
        assert_eq!(token.len(), 43);
        assert!(
            token
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
        );
    }

    #[test]
    fn token_is_single_use_and_expires() {
        let now = Rc::new(Cell::new(10.0));
        let clock = {
            let now = Rc::clone(&now);
            move || now.get()
        };
        let mut gate = PairingGate::with_clock(5.0, 5, clock);
        let token = gate.token.clone();
        assert!(gate.claim(&token));
        assert!(!gate.claim(&token));

        let now = Rc::new(Cell::new(10.0));
        let clock = {
            let now = Rc::clone(&now);
            move || now.get()
        };
        let mut expired = PairingGate::with_clock(5.0, 5, clock);
        now.set(15.0);
        let token = expired.token.clone();
        assert!(!expired.claim(&token));
    }

    #[test]
    fn failed_attempts_are_bounded() {
        let mut gate = PairingGate::new(300.0, 2);
        assert!(!gate.claim("salah"));
        assert!(!gate.claim("saláh"));
        let token = gate.token.clone();
        assert!(!gate.claim(&token));
        assert!(!gate.used);
        assert_eq!(gate.attempts, 0);
    }
}
