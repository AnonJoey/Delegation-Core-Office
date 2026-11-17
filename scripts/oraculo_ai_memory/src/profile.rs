// Trecho literal de crates/ai-memory-core/src/profile.rs, linhas 564 a 625, ai-memory 584ab792 (MIT, Fabio Akita).
#![allow(dead_code)]
/// The most words a field label has (`Status`, `Package manager`).
const FIELD_LABEL_MAX_WORDS: usize = 3;

/// The most words a terse field value has (`pnpm`, `run cargo fmt`). A
/// longer value is a sentence that reads on its own without its label.
const FIELD_VALUE_MAX_WORDS: usize = 4;

/// The labels ADR templates (MADR, Nygard, ai-memory's own durable-pages
/// skill) put on a page's metadata, lowercase.
const ADR_METADATA_LABELS: &[&str] = &[
    "status",
    "date",
    "deciders",
    "decision-makers",
    "authors",
    "author",
    "owner",
    "owners",
    "supersedes",
    "superseded by",
    "consulted",
    "informed",
    "tags",
    "last updated",
    "reviewers",
];

/// Whether `line` is a page metadata field such as `**Status:** Accepted`
/// or `**Date**: 2026-10-01`. It describes the page, so it is never the
/// page's statement. Only the label decides: a terse labelled rule
/// (`**Package manager:** pnpm`) is a statement, and a metadata value of
/// any length (`**Status:** accepted <!-- proposed | ... -->`) is not. The
/// form with the leading `**` already trimmed (`Status:** Accepted`), which
/// candidates harvested before this check still carry, counts too.
#[must_use]
pub fn is_metadata_field(line: &str) -> bool {
    labelled_field(line).is_some_and(|(label, _)| {
        let label = collapse_whitespace(label).to_ascii_lowercase();
        ADR_METADATA_LABELS.contains(&label.as_str())
    })
}

fn is_sentence(value: &str) -> bool {
    value.split_whitespace().count() > FIELD_VALUE_MAX_WORDS || value.ends_with(['.', '!'])
}

/// The label and value of a line that opens with an emphasized label,
/// `None` for any other line.
fn labelled_field(line: &str) -> Option<(&str, &str)> {
    let rest = line.trim().trim_start_matches(['-', '*', '_', ' ']);
    [":**", "**:", ":__", "__:"].iter().find_map(|close| {
        let (label, value) = rest.split_once(close)?;
        let words = label.split_whitespace().count();
        let plain = !label.contains(['*', '_', '.', '!', '?', ':', '`']);
        ((1..=FIELD_LABEL_MAX_WORDS).contains(&words) && plain)
            .then(|| (label.trim(), value.trim_start_matches(['*', '_']).trim()))
    })
}

fn collapse_whitespace(text: &str) -> String {
    text.split_whitespace().collect::<Vec<_>>().join(" ")
}
