// Trechos literais de crates/ai-memory-store/src/reader.rs (linhas 407 a 409, 441 a 548 e 569 a 592), ai-memory 584ab792 (MIT, Fabio Akita).
#![allow(dead_code)]
const AUTHORITY_CANDIDATE_MULTIPLIER: usize = 4;
const AUTHORITY_MIN_CANDIDATES: usize = 20;
const AUTHORITY_MAX_EXTRA_CANDIDATES: usize = 300;

#[derive(Debug, Clone, Copy)]
pub(crate) struct PageAuthority {
    pub(crate) factor: f64,
    /// Kind/tier penalty this page carries *because* it is a session page
    /// (`0.0` for every other kind). A `session_recall` query gives it back.
    pub(crate) session_penalty: f64,
}

impl PageAuthority {
    pub(crate) fn from_stored(
        path: &str,
        kind: &str,
        tier: &str,
        pinned: bool,
        frontmatter_json: &str,
    ) -> Self {
        // Relevance remains primary: even the strongest maintained page gets
        // at most a 1.5x boost, while explicit low-authority metadata bottoms
        // out at 0.55x rather than excluding the page.
        let mut factor = 1.0_f64;

        let kind_adjust = match kind {
            "rule" | "decision" => 0.15,
            "procedure" | "gotcha" | "preference" => 0.12,
            "concept" | "slot" => 0.07,
            "session" => -0.15,
            _ => 0.0,
        };
        let tier_adjust = match tier {
            "semantic" | "procedural" => 0.10,
            "episodic" => -0.08,
            "working" => -0.03,
            _ => 0.0,
        };
        factor += kind_adjust + tier_adjust;
        let session_penalty = if kind == "session" {
            -(kind_adjust + tier_adjust.min(0.0))
        } else {
            0.0
        };
        if pinned {
            factor += 0.08;
        }

        if path.starts_with("_lint/") {
            factor -= 0.20;
        } else if path.starts_with("investigations/") {
            factor -= 0.05;
        }

        let tags = authority_tags(frontmatter_json);
        if tags
            .iter()
            .any(|tag| tag == "canonical" || tag == "source-of-truth")
        {
            factor += 0.20;
        }
        if tags.iter().any(|tag| tag == "active") {
            factor += 0.05;
        }

        // Negative tags are explicit curator instructions. They cap the
        // result's authority instead of merely cancelling a canonical path
        // boost, but they never remove the page from search.
        if tags
            .iter()
            .any(|tag| tag == "do-not-answer-from" || tag == "test-fixture")
        {
            factor = factor.min(0.55);
        } else if tags.iter().any(|tag| tag == "superseded") {
            factor = factor.min(0.65);
        } else if tags.iter().any(|tag| tag == "historical") {
            factor = factor.min(0.80);
        }

        Self {
            factor: factor.clamp(0.55, 1.50),
            session_penalty,
        }
    }

    fn adjust_rank(&self, rank: f64) -> f64 {
        apply_rank_multiplier(rank, self.factor)
    }

    /// Effective multiplier when the query routed to session-recall
    /// retrieval: session pages get the kind/tier penalty they carry by
    /// default handed back plus `bonus`, still inside the bounds every
    /// other page lives in. Any other query leaves the factor alone.
    pub(crate) fn factor_for(&self, session_recall: bool, bonus: f64) -> f64 {
        if session_recall && self.session_penalty > 0.0 {
            (self.factor + self.session_penalty + bonus).clamp(0.55, 1.50)
        } else {
            self.factor
        }
    }
}

/// Scale a rank by a `> 0` multiplier so a larger multiplier always means a
/// better (lower) rank, whichever sign convention the rank arrived in: fused
/// RRF ranks are negated scores (`<= 0`), raw FTS5 ranks are positive.
pub(crate) fn apply_rank_multiplier(rank: f64, multiplier: f64) -> f64 {
    if rank <= 0.0 {
        rank * multiplier
    } else {
        rank / multiplier
    }
}

fn authority_tags(frontmatter_json: &str) -> Vec<String> {
    serde_json::from_str::<serde_json::Value>(frontmatter_json)
        .ok()
        .and_then(|frontmatter| frontmatter.get("tags").cloned())
        .and_then(|tags| tags.as_array().cloned())
        .unwrap_or_default()
        .into_iter()
        .filter_map(|tag| tag.as_str().map(normalize_authority_tag))
        .collect()
}

fn normalize_authority_tag(tag: &str) -> String {
    tag.trim().to_ascii_lowercase().replace('_', "-")
}

pub(crate) fn authority_candidate_limit(limit: usize) -> usize {
    if limit == 0 {
        return 0;
    }
    limit
        .saturating_mul(AUTHORITY_CANDIDATE_MULTIPLIER)
        .max(AUTHORITY_MIN_CANDIDATES)
        .min(limit.saturating_add(AUTHORITY_MAX_EXTRA_CANDIDATES))
}
