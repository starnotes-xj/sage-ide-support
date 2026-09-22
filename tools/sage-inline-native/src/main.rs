//! Dependency-free local scorer for the Sage inline-completion protocol.
//!
//! This binary is intentionally narrow: the IDE has already filtered every
//! candidate through exact concrete Sage type contracts.  We may rank that
//! finite set, but never emit arbitrary source text or start Sage/WSL.

use std::io::{self, BufRead, BufReader, BufWriter, Write};

const PROTOCOL: &str = "sage-inline-v1";
const MAX_LINE_BYTES: usize = 16 * 1024;
const MAX_CANDIDATES: usize = 512;
const MIN_CONTEXT_HITS: usize = 2;
const MIN_CONFIDENCE_MARGIN: usize = 2;

#[derive(Clone, Debug, Eq, PartialEq)]
struct Candidate {
    name: String,
    callable: bool,
}

fn main() {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut output = BufWriter::new(stdout.lock());

    for line in BufReader::new(stdin.lock()).lines() {
        let chosen = line
            .ok()
            .filter(|value| value.len() <= MAX_LINE_BYTES)
            .and_then(|value| handle_line(&value));
        let encoded = chosen.as_deref().map(hex_encode).unwrap_or_default();
        let _ = writeln!(output, "{PROTOCOL}\t{encoded}");
        let _ = output.flush();
    }
}

fn handle_line(line: &str) -> Option<String> {
    let mut fields = line.split('\t');
    if fields.next()? != PROTOCOL {
        return None;
    }
    let prefix = String::from_utf8(hex_decode(fields.next()?)?).ok()?;
    let candidates = parse_candidates(&hex_decode(fields.next()?)?)?;
    let context = String::from_utf8(hex_decode(fields.next()?)?).ok()?;
    if fields.next().is_some() {
        return None;
    }
    choose_candidate(&prefix, &candidates, &context)
}

fn parse_candidates(payload: &[u8]) -> Option<Vec<Candidate>> {
    let text = std::str::from_utf8(payload).ok()?;
    let candidates = text
        .lines()
        .map(|line| {
            let (name, callable) = line.split_once('\t')?;
            if name.is_empty() || !name.bytes().all(is_member_byte) {
                return None;
            }
            Some(Candidate {
                name: name.to_owned(),
                callable: match callable {
                    "0" => false,
                    "1" => true,
                    _ => return None,
                },
            })
        })
        .collect::<Option<Vec<_>>>()?;
    (!candidates.is_empty() && candidates.len() <= MAX_CANDIDATES).then_some(candidates)
}

fn choose_candidate(prefix: &str, candidates: &[Candidate], context: &str) -> Option<String> {
    let matching = candidates
        .iter()
        .filter(|candidate| candidate.name.starts_with(prefix))
        .collect::<Vec<_>>();
    if matching.len() == 1 {
        return Some(matching[0].name.clone());
    }

    let mut ranked = matching
        .iter()
        .map(|candidate| (candidate, member_hits(context.as_bytes(), candidate.name.as_bytes())))
        .collect::<Vec<_>>();
    ranked.sort_by(|(left_candidate, left_hits), (right_candidate, right_hits)| {
        right_hits
            .cmp(left_hits)
            .then_with(|| left_candidate.name.cmp(&right_candidate.name))
    });
    let (best, best_hits) = ranked.first()?;
    let runner_up_hits = ranked.get(1).map(|(_, hits)| *hits).unwrap_or_default();
    (*best_hits >= MIN_CONTEXT_HITS && *best_hits >= runner_up_hits + MIN_CONFIDENCE_MARGIN)
        .then(|| best.name.clone())
}

fn member_hits(context: &[u8], member: &[u8]) -> usize {
    let mut hits = 0;
    let mut start = 0;
    while start < context.len() {
        let Some(relative) = context[start..].windows(member.len() + 1).position(|window| {
            window[0] == b'.' && &window[1..] == member
        }) else {
            break;
        };
        let index = start + relative;
        let end = index + member.len() + 1;
        if context.get(end).is_none_or(|byte| !is_member_byte(*byte)) {
            hits += 1;
        }
        start = end;
    }
    hits
}

fn is_member_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

fn hex_decode(value: &str) -> Option<Vec<u8>> {
    if value.len() % 2 != 0 {
        return None;
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let high = (pair[0] as char).to_digit(16)?;
            let low = (pair[1] as char).to_digit(16)?;
            Some(((high << 4) | low) as u8)
        })
        .collect()
}

fn hex_encode(value: &str) -> String {
    value
        .as_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn candidates() -> Vec<Candidate> {
        vec![
            Candidate { name: "log".to_owned(), callable: true },
            Candidate { name: "local_coordinates".to_owned(), callable: true },
        ]
    }

    #[test]
    fn selects_the_only_type_filtered_candidate() {
        assert_eq!(
            choose_candidate("lo", &[Candidate { name: "log".to_owned(), callable: true }], ""),
            Some("log".to_owned()),
        );
    }

    #[test]
    fn uses_only_a_clear_local_context_winner() {
        assert_eq!(
            choose_candidate("lo", &candidates(), "P.log(G)\nP.log(G)\n"),
            Some("log".to_owned()),
        );
        assert_eq!(choose_candidate("lo", &candidates(), "P.log(G)\n"), None);
    }

    #[test]
    fn rejects_malformed_or_out_of_set_protocol_data() {
        assert_eq!(handle_line("unexpected\t6c6f\t\t"), None);
        assert_eq!(
            parse_candidates(b"good\t1\nbad-name\t1\n"),
            None,
        );
        assert_eq!(hex_decode("invalid"), None);
    }

    #[test]
    fn line_protocol_is_unambiguous_for_unicode_context() {
        let candidate_payload = hex_encode("log\t1\nlocal_coordinates\t1\n");
        let request = format!(
            "{PROTOCOL}\t{}\t{candidate_payload}\t{}",
            hex_encode("lo"),
            hex_encode("# 测试\nP.log(G)\nP.log(G)\n"),
        );
        assert_eq!(handle_line(&request), Some("log".to_owned()));
    }
}
