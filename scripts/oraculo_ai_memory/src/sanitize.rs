// Trecho literal de crates/ai-memory-core/src/sanitize.rs, linhas 418 a 441, ai-memory 584ab792 (MIT, Fabio Akita).
/// Truncate text to at most `max` UTF-8 bytes, reserving the ellipsis inside
/// the requested cap and never splitting a code point.
#[must_use]
pub fn truncate_utf8_bytes(input: &str, max: usize) -> String {
    if input.len() <= max {
        return input.to_string();
    }
    if max < '…'.len_utf8() {
        return String::new();
    }
    let limit = max - '…'.len_utf8();
    let mut end = 0;
    for (index, character) in input.char_indices() {
        let next = index + character.len_utf8();
        if next > limit {
            break;
        }
        end = next;
    }
    let mut output = String::with_capacity(max);
    output.push_str(&input[..end]);
    output.push('…');
    output
}
