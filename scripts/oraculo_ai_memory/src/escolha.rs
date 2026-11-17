// Trechos literais de crates/ai-memory-store/src/reader.rs (linhas 12820 a 12872 e 12959 a 13034), ai-memory 584ab792 (MIT, Fabio Akita).
#![allow(dead_code)]
use ai_memory_core::{Handoff, HandoffId, OwnerFilter};
/// Normalize a cwd for comparison: treat Windows backslashes as path
/// separators and trim trailing separators while keeping a bare root as `/`.
/// Drive-letter and UNC paths are ASCII-lowercased: the server often runs
/// on Linux (Docker Desktop) while the hook cwd is a Windows host path,
/// and Explorer/Git/PowerShell disagree on `C:` vs `c:`. Unix paths stay
/// byte-exact (`/Repo` is not `/repo`). Pure and string-only; it does not
/// touch the filesystem.
pub(crate) fn normalize_cwd(p: &str) -> std::borrow::Cow<'_, str> {
    let replaced = if p.contains('\\') {
        std::borrow::Cow::Owned(p.replace('\\', "/"))
    } else {
        std::borrow::Cow::Borrowed(p)
    };
    let trimmed = replaced.trim_end_matches('/');
    let core = if trimmed.is_empty() {
        std::borrow::Cow::Borrowed("/")
    } else if trimmed.len() == replaced.len() {
        replaced
    } else {
        std::borrow::Cow::Owned(trimmed.to_string())
    };
    if is_windows_style_path(&core) {
        std::borrow::Cow::Owned(core.to_ascii_lowercase())
    } else {
        core
    }
}

fn is_windows_style_path(path: &str) -> bool {
    let bytes = path.as_bytes();
    (bytes.len() >= 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':')
        || path.starts_with("//")
}

/// True when `descendant` is the same directory as `ancestor` or nested
/// below it, with component-boundary awareness: `/repo` contains
/// `/repo/api` but neither `/repo-other` nor `/repository`. Inputs are
/// normalized first. Pure; no SQL `LIKE`, so `%`/`_` in a path cannot act
/// as wildcards.
pub(crate) fn cwd_within(ancestor: &str, descendant: &str) -> bool {
    let a = normalize_cwd(ancestor);
    let d = normalize_cwd(descendant);
    if a == d {
        return true;
    }
    if a == "/" {
        // Root is an ancestor of every other absolute path.
        return d.starts_with('/') && d.len() > 1;
    }
    // Byte-prefix plus a `/` boundary right after it. `starts_with` is
    // byte-exact and `/` is ASCII, so this is UTF-8 safe.
    d.starts_with(a.as_ref()) && d.as_bytes().get(a.len()) == Some(&b'/')
}

pub(crate) fn is_handoff_candidate(h: &Handoff, cwd_filter: Option<&str>, owner_filter: &OwnerFilter) -> bool {
    // Ownership is checked FIRST, before the manual short-circuit below.
    // Order matters: a manual handoff is project-wide by cwd, so checking the
    // owner afterwards would let one operator's `memory_handoff_begin` be
    // claimed by the next session to start, whoever it belongs to - the exact
    // cross-operator mixing this filter exists to stop. Handoffs with no owner
    // (every pre-V39 row, and anything written without an actor) stay visible
    // to everyone, which preserves single-operator behaviour untouched.
    if !owner_filter.admits(h.origin.owner_user.as_deref()) {
        return false;
    }
    // Manual handoffs (memory_handoff_begin always sets from_session_id = None)
    // are project-wide and always candidates, whatever cwd they carry. Only auto
    // SessionEnd handoffs are cwd-path-boundary scoped. This makes "a manual
    // handoff always beats the auto one" deterministic on from_session_id,
    // instead of relying on a manual handoff happening to have a NULL cwd.
    if h.origin.from_session_id.is_none() {
        return true;
    }
    auto_handoff_matches_cwd(h.origin.cwd.as_deref(), cwd_filter)
}

/// Whether an automatic handoff is eligible for a session starting in
/// `cwd_filter`. Shared with the acceptance path so selection and supersession
/// apply exactly the same path-boundary rule.
pub(crate) fn auto_handoff_matches_cwd(
    handoff_cwd: Option<&str>,
    cwd_filter: Option<&str>,
) -> bool {
    match (cwd_filter, handoff_cwd) {
        // Project-wide read: every open handoff is a candidate.
        (None, _) => true,
        // No stored cwd: treat as project-wide.
        (_, None) => true,
        // cwd-bearing auto handoffs match by path-boundary.
        (Some(session_cwd), Some(handoff_cwd)) => cwd_within(handoff_cwd, session_cwd),
    }
}

pub(crate) fn handoff_selection_key(
    manual: bool,
    created_at_micros: i64,
    cwd: Option<&str>,
    id: HandoffId,
) -> (bool, i64, usize, [u8; 16]) {
    // Cwd specificity discriminates only equal-time AUTO handoffs. For manual
    // handoffs it must be neutral so the newest manual wins, not whichever
    // happens to carry the longest cwd. Normalize before counting so legacy
    // `/repo/` rows do not outrank equivalent `/repo` rows.
    let auto_specificity = if manual {
        0
    } else {
        cwd.map_or(0, |cwd| normalize_cwd(cwd).len())
    };
    (
        manual,            // manual beats auto
        created_at_micros, // newest
        auto_specificity,  // most specific equal-time auto cwd
        *id.as_bytes(),    // deterministic final tie-break
    )
}

pub(crate) fn prefer_handoff(a: &Handoff, b: &Handoff) -> std::cmp::Ordering {
    handoff_selection_key(
        a.origin.from_session_id.is_none(),
        a.lifecycle.created_at.as_microsecond(),
        a.origin.cwd.as_deref(),
        a.scope.id,
    )
    .cmp(&handoff_selection_key(
        b.origin.from_session_id.is_none(),
        b.lifecycle.created_at.as_microsecond(),
        b.origin.cwd.as_deref(),
        b.scope.id,
    ))
}
