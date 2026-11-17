//! Oraculo de paridade do porte do ai-memory para Python.
//!
//! Le uma linha de JSON por caso em stdin e escreve uma linha de JSON por resposta.
//! As funcoes chamadas aqui sao as do ai-memory, copiadas sem alteracao (ver os
//! cabecalhos de `src/*.rs`); este arquivo so liga a entrada e a saida.
#![allow(dead_code, unused_imports)]

mod autoridade;
mod brief_tiers;
mod compaction;
mod decay;
mod escolha;
mod excerpt;
mod keep_tokens;
mod profile;
mod recordar;
mod sanitize;
mod varredura;

use ai_memory_core::{
    FeedbackKind, Handoff, HandoffId, HandoffLifecycle, HandoffOrigin, HandoffScope, OwnerFilter, Tier, Timestamp,
};
use serde_json::{Value, json};
use std::io::{BufRead, Write};

fn tier(v: &Value) -> Tier {
    match v.as_str().unwrap_or("episodic") {
        "working" => Tier::Working,
        "semantic" => Tier::Semantic,
        "procedural" => Tier::Procedural,
        _ => Tier::Episodic,
    }
}

fn opt_f(v: &Value) -> Option<f64> {
    v.as_f64()
}

fn hex16(s: &str) -> [u8; 16] {
    let mut out = [0u8; 16];
    for i in 0..16 {
        out[i] = u8::from_str_radix(&s[2 * i..2 * i + 2], 16).unwrap();
    }
    out
}

fn tier_brief(t: brief_tiers::BriefTier) -> &'static str {
    use brief_tiers::BriefTier::*;
    match t {
        Omitted => "omitted",
        TitleOnly => "title_only",
        L0 => "l0",
        L1 => "l1",
        L2 => "l2",
    }
}

fn owner(v: &Value) -> OwnerFilter {
    match v.get("kind").and_then(Value::as_str).unwrap_or("any") {
        "unattributed" => OwnerFilter::Unattributed,
        "user" => OwnerFilter::User(v["user"].as_str().unwrap_or("").to_string()),
        _ => OwnerFilter::Any,
    }
}

fn handle(c: &Value) -> Value {
    match c["op"].as_str().unwrap_or("") {
        "retencao" => {
            let params: decay::DecayParams = serde_json::from_value(c["params"].clone()).unwrap();
            let r = decay::retention_score_with_breadth(
                &params,
                tier(&c["tier"]),
                c["age_days"].as_f64().unwrap(),
                c["access_count"].as_u64().unwrap() as u32,
                opt_f(&c["days_since_access"]),
                opt_f(&c["salience"]),
                c["distinct_actors"].as_u64().unwrap_or(0) as u32,
                c["breadth_weight"].as_f64().unwrap_or(0.0),
            );
            json!({ "valor": r })
        }
        "fria" => {
            let params: decay::DecayParams = serde_json::from_value(c["params"].clone()).unwrap();
            let cand = varredura::DecayCandidate {
                id: ai_memory_core::PageId(0),
                path: ai_memory_core::PagePath("x.md".to_string()),
                tier: tier(&c["tier"]),
                pinned: c["pinned"].as_bool().unwrap(),
                updated_at_us: c["updated_us"].as_i64().unwrap(),
                access_count: c["access_count"].as_u64().unwrap() as u32,
                last_accessed_at_us: c["last_access_us"].as_i64(),
                frontmatter_json: c["frontmatter_json"].as_str().unwrap().to_string(),
                expires_at_us: None,
                salience: opt_f(&c["salience"]),
                compacted_at_us: c["compacted_us"].as_i64(),
            };
            let mut breadth = std::collections::HashMap::new();
            breadth.insert(ai_memory_core::PageId(0), c["distinct_actors"].as_u64().unwrap_or(0) as u32);
            match varredura::cold_entry_for(&cand, &breadth, c["breadth_weight"].as_f64().unwrap_or(0.0), &params, c["now_us"].as_i64().unwrap()) {
                Some(e) => json!({ "fria": true, "retention": e.retention, "age_days": e.age_days, "access_count": e.access_count, "compacted": e.compacted_at_us.is_some() }),
                None => json!({ "fria": false }),
            }
        }
        "salience" => {
            let params: decay::DecayParams = serde_json::from_value(c["params"].clone()).unwrap();
            let kind = match c["kind"].as_str().unwrap() {
                "helpful" => FeedbackKind::Helpful,
                "not_helpful" => FeedbackKind::NotHelpful,
                "stale" => FeedbackKind::Stale,
                _ => FeedbackKind::Wrong,
            };
            json!({ "valor": decay::salience_after_feedback(&params, opt_f(&c["current"]), kind) })
        }
        "lambda" => json!({ "valor": decay::lambda_from_half_life_days(c["dias"].as_f64().unwrap()) }),
        "tokens" => json!({ "valor": keep_tokens::mine_keep_tokens(c["body"].as_str().unwrap()) }),
        "residuo" => json!({ "valor": keep_tokens::mine_residue_tokens(c["body"].as_str().unwrap(), c["max"].as_u64().unwrap() as usize) }),
        "compactar" => {
            let (fm, body) = compaction::build_compacted_markdown(&c["frontmatter"], c["body"].as_str().unwrap());
            json!({ "frontmatter": fm, "body": body })
        }
        "trecho" => {
            let e = excerpt::excerpt_from_page(&c["frontmatter"], c["body"].as_str().unwrap());
            json!({ "l0": e.l0, "l1": e.l1 })
        }
        "prosa" => json!({ "valor": excerpt::leading_prose(c["body"].as_str().unwrap()) }),
        "meta" => json!({ "valor": profile::is_metadata_field(c["line"].as_str().unwrap()) }),
        "truncar" => json!({ "valor": sanitize::truncate_utf8_bytes(c["input"].as_str().unwrap(), c["max"].as_u64().unwrap() as usize) }),
        "niveis" => {
            let pages: Vec<brief_tiers::PageCosts> = c["pages"]
                .as_array()
                .unwrap()
                .iter()
                .map(|p| brief_tiers::PageCosts {
                    privileged: p["privileged"].as_bool().unwrap(),
                    title_only: p["title_only"].as_u64().unwrap() as usize,
                    tiers: p["tiers"].as_array().map(|a| {
                        [a[0].as_u64().unwrap() as usize, a[1].as_u64().unwrap() as usize, a[2].as_u64().unwrap() as usize]
                    }),
                })
                .collect();
            let b = &c["budget"];
            let budget = brief_tiers::BriefBudget {
                prefix: b["prefix"].as_u64().unwrap() as usize,
                content_ceiling: b["content_ceiling"].as_u64().unwrap() as usize,
                recent_full: b["recent_full"].as_u64().unwrap() as usize,
                recent_first: b["recent_first"].as_u64().unwrap() as usize,
            };
            let n = pages.len();
            let base = c["omitted_base"].as_u64().unwrap() as usize;
            let listed = c["listed"].as_u64().unwrap() as usize;
            let count_only = c["count_only"].as_u64().unwrap() as usize;
            let plan = brief_tiers::assign_tiers(&pages, budget, |from| base + listed * (n - from), |_| count_only);
            json!({
                "tiers": plan.tiers.iter().map(|t| tier_brief(*t)).collect::<Vec<_>>(),
                "omitted_from": plan.omitted_from,
                "recent_reserve": plan.recent_reserve,
            })
        }
        "autoridade" => {
            let a = autoridade::PageAuthority::from_stored(
                c["path"].as_str().unwrap(),
                c["kind"].as_str().unwrap(),
                c["tier"].as_str().unwrap(),
                c["pinned"].as_bool().unwrap(),
                c["frontmatter"].as_str().unwrap(),
            );
            json!({
                "factor": a.factor,
                "session_penalty": a.session_penalty,
                "factor_recall": a.factor_for(true, c["bonus"].as_f64().unwrap_or(0.25)),
                "factor_normal": a.factor_for(false, c["bonus"].as_f64().unwrap_or(0.25)),
            })
        }
        "alfabeticos" => {
            // As faixas de pontos de codigo para os quais `char::is_alphabetic` e verdadeiro.
            let mut faixas: Vec<[u32; 2]> = Vec::new();
            for cp in 0u32..=0x10FFFF {
                if let Some(ch) = char::from_u32(cp) {
                    if ch.is_alphabetic() {
                        match faixas.last_mut() {
                            Some(f) if f[1] + 1 == cp => f[1] = cp,
                            _ => faixas.push([cp, cp]),
                        }
                    }
                }
            }
            json!({ "faixas": faixas })
        }
        "sessao" => json!({ "valor": recordar::is_session_recall_query(c["query"].as_str().unwrap()) }),
        "rank" => json!({ "valor": autoridade::apply_rank_multiplier(c["rank"].as_f64().unwrap(), c["mult"].as_f64().unwrap()) }),
        "limite" => json!({ "valor": autoridade::authority_candidate_limit(c["limit"].as_u64().unwrap() as usize) }),
        "cwd_normalizar" => json!({ "valor": escolha::normalize_cwd(c["p"].as_str().unwrap()).to_string() }),
        "cwd_dentro" => json!({ "valor": escolha::cwd_within(c["a"].as_str().unwrap(), c["d"].as_str().unwrap()) }),
        "casa" => json!({ "valor": escolha::auto_handoff_matches_cwd(c["handoff_cwd"].as_str(), c["filtro"].as_str()) }),
        "chave" => {
            let id = HandoffId(hex16(c["id"].as_str().unwrap()));
            let k = escolha::handoff_selection_key(c["manual"].as_bool().unwrap(), c["criado"].as_i64().unwrap(), c["cwd"].as_str(), id);
            let hex: String = k.3.iter().map(|b| format!("{b:02x}")).collect();
            json!({ "valor": [k.0, k.1, k.2, hex] })
        }
        "escolher" => {
            let filtro = c["filtro"].as_str();
            let dono = owner(&c["dono"]);
            let hs: Vec<Handoff> = c["handoffs"]
                .as_array()
                .unwrap()
                .iter()
                .map(|h| Handoff {
                    scope: HandoffScope { id: HandoffId(hex16(h["id"].as_str().unwrap())) },
                    origin: HandoffOrigin {
                        from_session_id: if h["manual"].as_bool().unwrap() { None } else { Some("s".to_string()) },
                        cwd: h["cwd"].as_str().map(str::to_string),
                        owner_user: h["dono"].as_str().map(str::to_string),
                    },
                    lifecycle: HandoffLifecycle { created_at: Timestamp(h["criado"].as_i64().unwrap()) },
                })
                .collect();
            let escolhido = hs
                .into_iter()
                .filter(|h| escolha::is_handoff_candidate(h, filtro, &dono))
                .max_by(escolha::prefer_handoff);
            json!({ "valor": escolhido.map(|h| h.scope.id.0.iter().map(|b| format!("{b:02x}")).collect::<String>()) })
        }
        outro => json!({ "erro": format!("operacao desconhecida: {outro}") }),
    }
}

fn main() {
    let stdin = std::io::stdin();
    let mut out = std::io::BufWriter::new(std::io::stdout().lock());
    for linha in stdin.lock().lines() {
        let linha = linha.unwrap();
        if linha.trim().is_empty() {
            continue;
        }
        let caso: Value = serde_json::from_str(&linha).unwrap();
        let r = handle(&caso);
        writeln!(out, "{}", r).unwrap();
    }
}
