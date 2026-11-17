"""Arquivos Python do Headroom (headroomlabs-ai/headroom, Apache 2.0) copiados SEM modificacao.

- `content_detector.py`: detecta o tipo da saida (json, diff, html, busca,
  log, codigo, tabela, config, texto). E a versao Python de referencia, mais
  nova que a portada em Rust no proprio Headroom.
- `lossless_compaction.py`: compactacao reversivel e autoverificada (desfaz e
  confere antes de aceitar), que nunca emite marca de recuperacao.

Origem: `headroom/transforms/` do branch main baixado em 2026-09-30. Licenca
em `THIRD_PARTY_LICENSES/Headroom-LICENSE-Apache-2.0`, aviso em
`Headroom-NOTICE`. Para atualizar, copie de novo; nao edite aqui.
"""
