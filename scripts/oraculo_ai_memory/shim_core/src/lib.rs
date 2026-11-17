//! Casca minima dos tipos do `ai-memory-core` usados pelas funcoes puras copiadas
//! para o oraculo. Os nomes e os campos sao os do original (ai-memory 584ab792, MIT,
//! Fabio Akita); so ficou o que o codigo copiado toca.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Tier {
    Working,
    Episodic,
    Semantic,
    Procedural,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FeedbackKind {
    Helpful,
    NotHelpful,
    Stale,
    Wrong,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum OwnerFilter {
    User(String),
    Unattributed,
    Any,
}

impl OwnerFilter {
    /// Igual a `OwnerFilter::admits` de crates/ai-memory-core/src/actor.rs.
    pub fn admits(&self, owner: Option<&str>) -> bool {
        match (self, owner) {
            (_, None) | (Self::Any, _) => true,
            (Self::User(me), Some(owner)) => me == owner,
            (Self::Unattributed, Some(_)) => false,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct HandoffId(pub [u8; 16]);

impl HandoffId {
    pub fn as_bytes(&self) -> &[u8; 16] {
        &self.0
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Timestamp(pub i64);

impl Timestamp {
    pub fn as_microsecond(&self) -> i64 {
        self.0
    }
}

pub struct HandoffScope {
    pub id: HandoffId,
}

pub struct HandoffOrigin {
    pub from_session_id: Option<String>,
    pub cwd: Option<String>,
    pub owner_user: Option<String>,
}

pub struct HandoffLifecycle {
    pub created_at: Timestamp,
}

pub struct Handoff {
    pub scope: HandoffScope,
    pub origin: HandoffOrigin,
    pub lifecycle: HandoffLifecycle,
}

/// Casca de `PageId` (ai-memory-core/src/ids.rs): so a igualdade e o hash importam para a varredura.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct PageId(pub u32);

/// Casca de `PagePath`: so `as_str` importa para a varredura.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct PagePath(pub String);

impl PagePath {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}
