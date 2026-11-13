//! Short-lived pairing invitations pinned to the sender's TLS certificate.
//!
//! The wire format is intentionally identical to the Python implementation
//! (`cm1:` + unpadded base64url JSON) so both versions can talk to each other
//! during the migration.

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use serde::{Deserialize, Serialize};
use std::fmt;
use std::net::Ipv4Addr;

/// Maximum accepted invitation length before decoding.
pub const MAX_INVITATION_LEN: usize = 2048;

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum InvitationError {
    #[error("Gunakan alamat IPv4 komputer pengirim di jaringan lokal.")]
    BadAddress,
    #[error("Port tidak valid.")]
    BadPort,
    #[error("Identitas sertifikat tidak valid.")]
    BadFingerprint,
    #[error("Token pairing tidak valid.")]
    BadToken,
    #[error("Undangan tidak valid. Salin seluruh undangan dari pengirim.")]
    Malformed,
}

/// A single-use invitation for one receiver.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Invitation {
    pub host: String,
    pub port: u16,
    pub fingerprint: String,
    pub token: String,
}

impl Invitation {
    /// Validate every field and build an invitation.
    pub fn new(
        host: impl Into<String>,
        port: u16,
        fingerprint: impl Into<String>,
        token: impl Into<String>,
    ) -> Result<Self, InvitationError> {
        let invitation = Self {
            host: host.into(),
            port,
            fingerprint: fingerprint.into(),
            token: token.into(),
        };
        invitation.validate()?;
        Ok(invitation)
    }

    fn validate(&self) -> Result<(), InvitationError> {
        let ip: Ipv4Addr = self.host.parse().map_err(|_| InvitationError::BadAddress)?;
        if ip.is_unspecified() || ip.is_multicast() || ip.is_broadcast() || is_reserved(ip) {
            return Err(InvitationError::BadAddress);
        }
        if self.port == 0 {
            return Err(InvitationError::BadPort);
        }
        if self.fingerprint.len() != 64
            || !self
                .fingerprint
                .bytes()
                .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
        {
            return Err(InvitationError::BadFingerprint);
        }
        if self.token.len() != 43
            || !self
                .token
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
        {
            return Err(InvitationError::BadToken);
        }
        Ok(())
    }

    /// Encode as `cm1:<base64url>` without padding.
    pub fn encode(&self) -> String {
        let json = serde_json::to_vec(self).expect("invitation fields are serializable");
        format!("cm1:{}", URL_SAFE_NO_PAD.encode(json))
    }

    /// Decode and fully validate a pasted invitation.
    pub fn decode(value: &str) -> Result<Self, InvitationError> {
        let value = value.trim();
        if value.len() > MAX_INVITATION_LEN || !value.starts_with("cm1:") {
            return Err(InvitationError::Malformed);
        }
        let raw = URL_SAFE_NO_PAD
            .decode(&value[4..])
            .map_err(|_| InvitationError::Malformed)?;
        let invitation: Self =
            serde_json::from_slice(&raw).map_err(|_| InvitationError::Malformed)?;
        invitation.validate()?;
        Ok(invitation)
    }
}

/// Match Python's `IPv4Address.is_reserved` without unstable std APIs.
fn is_reserved(ip: Ipv4Addr) -> bool {
    let [first, second, third, _] = ip.octets();
    first >= 240 || (first == 192 && second == 0 && third == 0)
}

impl fmt::Display for Invitation {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.encode())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip() {
        let invitation =
            Invitation::new("192.168.1.20", 8765, "a".repeat(64), "B".repeat(43)).unwrap();
        assert_eq!(
            Invitation::decode(&invitation.encode()).unwrap(),
            invitation
        );
    }

    #[test]
    fn rejects_untrusted_shapes() {
        for value in ["", "https://example.com", "cm1:%%%%", "cm1:e30"] {
            assert!(Invitation::decode(value).is_err(), "{value}");
        }
        let too_long = format!("cm1:{}", "a".repeat(2100));
        assert_eq!(
            Invitation::decode(&too_long),
            Err(InvitationError::Malformed)
        );
    }

    #[test]
    fn rejects_bad_addresses_and_identity() {
        for host in ["0.0.0.0", "224.0.0.1", "example.com", "127.0.0.1/path"] {
            assert_eq!(
                Invitation::new(host, 8765, "a".repeat(64), "B".repeat(43)),
                Err(InvitationError::BadAddress),
                "{host}"
            );
        }
        assert!(Invitation::new("127.0.0.1", 0, "a".repeat(64), "B".repeat(43)).is_err());
        assert!(Invitation::new("127.0.0.1", 8765, "invalid", "B".repeat(43)).is_err());
        assert!(Invitation::new("127.0.0.1", 8765, "a".repeat(64), "short").is_err());
    }

    #[test]
    fn python_wire_format_is_compatible() {
        // Produced by the Python implementation for the same fields.
        let encoded = Invitation::new("192.168.1.20", 8765, "a".repeat(64), "B".repeat(43))
            .unwrap()
            .encode();
        assert!(encoded.starts_with("cm1:"));
        assert_eq!(
            encoded,
            "cm1:eyJob3N0IjoiMTkyLjE2OC4xLjIwIiwicG9ydCI6ODc2NSwiZmluZ2VycHJpbnQiOiJhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhIiwidG9rZW4iOiJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCIn0"
        );
    }
}
