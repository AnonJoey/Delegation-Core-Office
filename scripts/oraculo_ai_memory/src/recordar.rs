// Trecho literal de crates/ai-memory-store/src/retrieval_tuning.rs, linhas 91 a 180, ai-memory 584ab792 (MIT, Fabio Akita).
#![allow(dead_code)]
// Markers are matched on the lower-cased query. CJK phrases match as plain
// substrings; Latin phrases match on word boundaries so "now" never fires
// inside "known" or "snow". "会话" (session) only counts in a recall frame
// ("的会话 / 次会话 / 会话里"), so a query *about* sessions as a topic -
// "user_sessions 异常会话" - is not routed to past-session recall.
const SESSION_RECALL_ZH: &[&str] = &[
    "之前",
    "上次",
    "上回",
    "上一次",
    "那次",
    "那回",
    "前几天",
    "前天",
    "昨天",
    "那天",
    "上周",
    "上星期",
    "上个月",
    "的会话",
    "次会话",
    "个会话",
    "会话里",
    "会话中",
    "历史会话",
    "当时我们",
    "我们当时",
];
const SESSION_RECALL_EN: &[&str] = &[
    "last time",
    "last session",
    "previous session",
    "earlier session",
    "that session",
    "the session where",
    "yesterday",
    "the other day",
    "last week",
    "when we",
    "we did",
    "did we",
    "what did we",
    "how did we",
    "back then",
    "earlier we",
    "previously",
];
// Require an explicit historical phrase: "sessão", "antes", or "ontem"
// alone also occur in technical queries unrelated to recalling our work.
const SESSION_RECALL_PT_BR: &[&str] = &[
    "última sessão",
    "ultima sessao",
    "última sessao",
    "ultima sessão",
    "sessão anterior",
    "sessao anterior",
    "onde paramos ontem",
    "decisão anterior",
    "decisao anterior",
];

/// Route a query to session-recall retrieval by lexical markers. Deliberately
/// zero-LLM: it gates a bounded ranking nudge, not a retrieval mode, and a
/// false positive costs a few rank positions rather than a wrong answer.
#[must_use]
pub fn is_session_recall_query(query: &str) -> bool {
    let lowered = query.to_lowercase();
    let padded = latin_word_padded(&lowered);
    SESSION_RECALL_ZH.iter().any(|m| lowered.contains(m))
        || SESSION_RECALL_EN
            .iter()
            .chain(SESSION_RECALL_PT_BR.iter())
            .any(|m| padded.contains(&format!(" {m} ")))
}

/// Replace every non-alphanumeric Latin character with a space and pad the
/// ends, so multi-word markers can be matched as ` word word `.
fn latin_word_padded(lowered: &str) -> String {
    let mut out = String::with_capacity(lowered.len() + 2);
    out.push(' ');
    for ch in lowered.chars() {
        if ch.is_ascii_alphanumeric() || (!ch.is_ascii() && ch.is_alphabetic()) {
            out.push(ch);
        } else {
            out.push(' ');
        }
    }
    out.push(' ');
    out
}
