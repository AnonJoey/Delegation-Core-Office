// Trechos literais de crates/ai-memory-consolidate/src/sweep.rs (linhas 1117 a 1167 e 1495 a 1513) e de
// crates/ai-memory-store/src/reader.rs (linhas 12612 a 12642), ai-memory 584ab792 (MIT, Fabio Akita).
// `DecayCandidate` perde os atributos `derive(Serialize)`; `US_PER_DAY` vem da linha 340 do sweep.rs.
#![allow(dead_code)]
use crate::decay::{DecayParams, retention_score_with_breadth};
use ai_memory_core::{PageId, PagePath, Tier};
use std::collections::HashMap;

const US_PER_DAY: f64 = 86_400_000_000.0;

pub struct DecayCandidate {
    pub id: PageId,
    pub path: PagePath,
    pub tier: ai_memory_core::Tier,
    pub pinned: bool,
    pub updated_at_us: i64,
    pub access_count: u32,
    pub last_accessed_at_us: Option<i64>,
    pub frontmatter_json: String,
    pub expires_at_us: Option<i64>,
    pub salience: Option<f64>,
    pub compacted_at_us: Option<i64>,
}

pub(crate) struct ColdEntry {
    pub(crate) id: PageId,
    pub(crate) path: PagePath,
    pub(crate) retention: f64,
    pub(crate) age_days: f64,
    pub(crate) access_count: u32,
    pub(crate) compacted_at_us: Option<i64>,
}

pub(crate) fn cold_entry_for(
    c: &DecayCandidate,
    breadth: &HashMap<PageId, u32>,
    breadth_weight: f64,
    params: &DecayParams,
    now_us: i64,
) -> Option<ColdEntry> {
    if !is_decayable(c) {
        return None;
    }
    let age_days = elapsed_days(now_us, c.updated_at_us);
    let days_since_access = c.last_accessed_at_us.map(|us| elapsed_days(now_us, us));
    let score = retention_score_with_breadth(
        params,
        c.tier,
        age_days,
        c.access_count,
        days_since_access,
        c.salience,
        breadth.get(&c.id).copied().unwrap_or(0),
        breadth_weight,
    );
    if score < params.cold_threshold {
        Some(ColdEntry {
            id: c.id,
            path: c.path.clone(),
            retention: score,
            age_days,
            access_count: c.access_count,
            compacted_at_us: c.compacted_at_us,
        })
    } else {
        None
    }
}

fn elapsed_days(now_us: i64, then_us: i64) -> f64 {
    #[allow(clippy::cast_precision_loss)]
    let raw = (now_us - then_us) as f64 / US_PER_DAY;
    raw.max(0.0)
}

fn is_decayable(c: &DecayCandidate) -> bool {
    if c.tier != Tier::Episodic {
        return false;
    }
    if c.pinned {
        return false;
    }
    if let Ok(fm) = serde_json::from_str::<serde_json::Value>(&c.frontmatter_json)
        && fm.get("pinned").and_then(serde_json::Value::as_bool) == Some(true)
    {
        return false;
    }
    true
}
