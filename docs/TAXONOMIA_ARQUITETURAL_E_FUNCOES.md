# Taxonomia Arquitetural e Catálogo Funcional do Codebase delegation-core

- **Data da Catalogação**: 2026-10-22
- **Motor de Inferência e Classificação**: Qwen2.5-Coder-14B-Instruct-Q4_K_M (Execução Local via GPU RTX 4070, 16.384 contexto)
- **Escopo**: 100% dos módulos Python (`src/delegation_core`) mapeados via AST

---

## 1. Visão Geral da Arquitetura

O `delegation-core` é composto por **115 módulos Python**, totalizando **58,891 linhas de código** e **1,415 funções e métodos catalogados**.
Todo o repositório foi decomposto em domínios de arquitetura de alta coesão e baixo acoplamento:

| Domínio Funcional | Módulos | Funções / Métodos | Linhas de Código (LOC) | Proporção do Código |
| :--- | :---: | :---: | :---: | :---: |
| **Knowledge Graph & AST** | 52 | 574 | 32,757 | 55.6% |
| **Vault & Storage** | 16 | 183 | 6,947 | 11.8% |
| **Core & Daemon** | 11 | 103 | 3,109 | 5.3% |
| **Hooks & Integrations** | 9 | 84 | 2,446 | 4.2% |
| **Search & Embeddings** | 7 | 122 | 2,578 | 4.4% |
| **MCP Protocol & Server** | 5 | 100 | 2,687 | 4.6% |
| **Queue & Background Tasks** | 5 | 38 | 1,225 | 2.1% |
| **CLI & Management** | 4 | 151 | 5,291 | 9.0% |
| **Security & Auth** | 3 | 17 | 632 | 1.1% |
| **Utilities & Helpers** | 2 | 1 | 92 | 0.2% |
| **Dashboard & Telemetry** | 1 | 42 | 1,127 | 1.9% |

---

## 2. Distribuição por Papel Técnico das Funções (`role_category`)

| Papel Técnico da Função | Ocorrências | Proporção |
| :--- | :---: | :---: |
| `Parser / AST / Extração` | **285** | 20.1% |
| `Leitura / Consulta` | **277** | 19.6% |
| `Mutação / Escrita` | **189** | 13.4% |
| `Utilitário / Helper` | **171** | 12.1% |
| `Orquestração / Lifecycle` | **137** | 9.7% |
| `Validação / Segurança` | **114** | 8.1% |
| `Cálculo / Algoritmo` | **43** | 3.0% |
| `Handler MCP / Endpoint` | **37** | 2.6% |
| `Utility` | **11** | 0.8% |
| `Exportação` | **10** | 0.7% |
| `Type Extraction` | **10** | 0.7% |
| `Name Extraction` | **9** | 0.6% |
| `Vault Management` | **8** | 0.6% |
| `Background Task` | **7** | 0.5% |
| `Graph Management` | **5** | 0.4% |
| `Type Analysis` | **5** | 0.4% |
| `Data Ingestion` | **4** | 0.3% |
| `Node Handling` | **4** | 0.3% |
| `Process Management` | **4** | 0.3% |
| `Sanitização` | **4** | 0.3% |
| `Task Management` | **4** | 0.3% |
| `Type Collection` | **4** | 0.3% |
| `Configuration` | **3** | 0.2% |
| `Configuração / Setup` | **3** | 0.2% |
| `Language Specific Handler` | **3** | 0.2% |
| `Workspace Management` | **3** | 0.2% |
| `Data Retrieval` | **2** | 0.1% |
| `Health Check` | **2** | 0.1% |
| `Identifier Collection` | **2** | 0.1% |
| `Import Detection` | **2** | 0.1% |
| `Job Management` | **2** | 0.1% |
| `Maintenance` | **2** | 0.1% |
| `Name Binding` | **2** | 0.1% |
| `Receiver Analysis` | **2** | 0.1% |
| `Search` | **2** | 0.1% |
| `Server Management` | **2** | 0.1% |
| `Type Parameter Analysis` | **2** | 0.1% |
| `Analysis` | **1** | 0.1% |
| `Annotation Analysis` | **1** | 0.1% |
| `Assignment Classification` | **1** | 0.1% |
| `Attribute Analysis` | **1** | 0.1% |
| `Call Detection` | **1** | 0.1% |
| `Class Name Extractor` | **1** | 0.1% |
| `Classification` | **1** | 0.1% |
| `Client Management` | **1** | 0.1% |
| `Constant Name Extractor` | **1** | 0.1% |
| `Data Compression` | **1** | 0.1% |
| `Data Persistence` | **1** | 0.1% |
| `Data Processing` | **1** | 0.1% |
| `Declaration Classification` | **1** | 0.1% |
| `Declarator Analysis` | **1** | 0.1% |
| `Decorator Collector` | **1** | 0.1% |
| `Decorator Edge Emitter` | **1** | 0.1% |
| `Decorator Name Extractor` | **1** | 0.1% |
| `Execution` | **1** | 0.1% |
| `Generic AST Extractor` | **1** | 0.1% |
| `Inheritance Analysis` | **1** | 0.1% |
| `Interface Analysis` | **1** | 0.1% |
| `Lambda Analysis` | **1** | 0.1% |
| `Listing` | **1** | 0.1% |
| `Local Class Binding Mapper` | **1** | 0.1% |
| `Method Name Extractor` | **1** | 0.1% |
| `Monitoramento / Telemetria` | **1** | 0.1% |
| `Name Analysis` | **1** | 0.1% |
| `Node Search` | **1** | 0.1% |
| `Parameter Extraction` | **1** | 0.1% |
| `Pre-Scan` | **1** | 0.1% |
| `Return Type Analysis` | **1** | 0.1% |
| `Server Operation` | **1** | 0.1% |
| `Session Management` | **1** | 0.1% |
| `Statistics` | **1** | 0.1% |
| `Status Check` | **1** | 0.1% |
| `System Information` | **1** | 0.1% |
| `Teste / Debug` | **1** | 0.1% |
| `Type Resolver` | **1** | 0.1% |
| `Validation` | **1** | 0.1% |

---

## 3. Catálogo Detalhado de Módulos e Funções por Domínio

### Domínio: `Knowledge Graph & AST`
> **Módulos**: 52 | **Funções**: 574 | **LOC**: 32,757

#### Módulo: `graph/__init__.py` (39 LOC)
**Responsabilidade**: Módulo responsável por extrair, construir, clusterizar, analisar e relatar gráficos.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__getattr__()` | *top_level* | `Parser / AST / Extração` | Função para obter atributos dinamicamente. |

#### Módulo: `graph/affected.py` (272 LOC)
**Responsabilidade**: Funções para identificar e formatar nós afetados em um grafo.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_bare_name()` | *top_level* | `Parser / AST / Extração` | Extrai o nome básico de um nó, removendo decorações. |
| `_format_location()` | *top_level* | `Utilitário / Helper` | Formata a localização de um nó. |
| `_node_label()` | *top_level* | `Parser / AST / Extração` | Extrai o rótulo de um nó. |
| `_normalize_label()` | *top_level* | `Parser / AST / Extração` | Normaliza o rótulo de um nó. |
| `_prefer_file_node()` | *top_level* | `Orquestração / Lifecycle` | Preferencia para nós de nível de arquivo quando há múltiplos nós correspondentes. |
| `affected_nodes()` | *top_level* | `Leitura / Consulta` | Identifica nós afetados no grafo. |
| `format_affected()` | *top_level* | `Utilitário / Helper` | Formata a informação de nós afetados. |
| `load_graph()` | *top_level* | `Leitura / Consulta` | Carrega um grafo a partir de um arquivo. |
| `resolve_seed()` | *top_level* | `Orquestração / Lifecycle` | Resolve o nó inicial para análise. |

#### Módulo: `graph/analyze.py` (741 LOC)
**Responsabilidade**: Análise de grafo para identificar nós importantes e conexões surpreendentes.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_cross_community_surprises()` | *top_level* | `Leitura / Consulta` | Identifica conexões surpreendentes entre comunidades. |
| `_cross_file_surprises()` | *top_level* | `Leitura / Consulta` | Identifica conexões surpreendentes entre arquivos. |
| `_cross_language()` | *top_level* | `Validação / Segurança` | Verifica se dois arquivos pertencem a famílias linguísticas diferentes. |
| `_file_category()` | *top_level* | `Parser / AST / Extração` | Determina a categoria de um arquivo. |
| `_is_concept_node()` | *top_level* | `Validação / Segurança` | Verifica se um nó é um nó conceitual. |
| `_is_file_node()` | *top_level* | `Validação / Segurança` | Verifica se um nó é um nó de nível de arquivo. |
| `_is_json_key_node()` | *top_level* | `Validação / Segurança` | Verifica se um nó é uma chave JSON. |
| `_node_community_map()` | *top_level* | `Parser / AST / Extração` | Mapeia nós para comunidades. |
| `_surprise_score()` | *top_level* | `Cálculo / Algoritmo` | Calcula a pontuação de surpresa para uma conexão entre arquivos. |
| `_top_level_dir()` | *top_level* | `Parser / AST / Extração` | Extrai o diretório de nível superior de um caminho. |
| `find_import_cycles()` | *top_level* | `Leitura / Consulta` | Detecta ciclos de importação no nível de arquivo. |
| `god_nodes()` | *top_level* | `Leitura / Consulta` | Identifica os nós mais conectados no grafo. |
| `graph_diff()` | *top_level* | `Leitura / Consulta` | Compara duas snapshots de grafo e retorna as diferenças. |
| `suggest_questions()` | *top_level* | `Utilitário / Helper` | Gera perguntas baseadas no grafo. |
| `surprising_connections()` | *top_level* | `Leitura / Consulta` | Encontra conexões surpreendentes no grafo. |

#### Módulo: `graph/build.py` (1321 LOC)
**Responsabilidade**: Módulo responsável pela construção e manipulação de grafos, incluindo normalização de nós e arestas, desambiguação de rótulos de arquivos e fusão de múltiplos resultados de extração em um único grafo.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_abs_identity()` | *top_level* | `Parser / AST / Extração` | Retorna uma forma insensível a formatação de identidade absoluta para um source_file. |
| `_disambiguate_file_node_labels()` | *top_level* | `Mutação / Escrita` | Relabela nós de arquivo com nomes de base colidindo em um grafo (#2032). Ids/edges são. |
| `_doc_twin_remap()` | *top_level* | `Parser / AST / Extração` | Mapeia um nó de documento rápido de varredura de markdown ``<slug>`` para o semântico. |
| `_file_label_reassignments()` | *top_level* | `Mutação / Escrita` | Dado (chave, rótulo, source_file) triplos, retorna {chave: novo_rótulo} para arquivos. |
| `_infer_merge_root()` | *top_level* | `Parser / AST / Extração` | Melhor esforço para escanear a raiz para relativizar caminhos em build_merge quando o chamador. |
| `_is_file_node_label()` | *top_level* | `Validação / Segurança` | Verifica se *label* é um rótulo de nó de arquivo para *source_file* — o nome simples. |
| `_norm_label()` | *top_level* | `Parser / AST / Extração` | Chave de dedup canônica — ciente de Unicode, preserva CJK/caracteres de palavra. |
| `_norm_source_file()` | *top_level* | `Parser / AST / Extração` | Normaliza separadores de caminho e relativiza caminhos absolutos. |
| `_normalize_hyperedge_members()` | *top_level* | `Mutação / Escrita` | Canonicaliza a lista de membros de uma hiperaresta na chave `nodes`, in place. |
| `_old_file_stems()` | *top_level* | `Parser / AST / Extração` | Forma de fragmento semântico pré-migração que ``rel`` pode ter usado. |
| `_semantic_id_remap()` | *top_level* | `Parser / AST / Extração` | Re-deriva ids de nós não-AST de ``source_file`` usando o canônico. |
| `_shortest_unique_suffix()` | *top_level* | `Parser / AST / Extração` | Suffixo de caminho mais curto (basename + k diretórios pai) de *sf* que é. |
| `build()` | *top_level* | `Handler MCP / Endpoint` | Mescla múltiplos resultados de extração em um único grafo. |
| `build_from_json()` | *top_level* | `Handler MCP / Endpoint` | Constrói um grafo NetworkX de um dicionário de extração. |
| `build_merge()` | *top_level* | `Handler MCP / Endpoint` | Carrega graph.json existente, mescla novos chunks nele e salva de volta. |
| `dedupe_edges()` | *top_level* | `Mutação / Escrita` | Colapsa arestas paralelas exatas por ``(source, target, relation)``, mantendo a. |
| `dedupe_nodes()` | *top_level* | `Mutação / Escrita` | Colapsa nós compartilhando um ``id``, last-writer-wins em atributos. |
| `deduplicate_by_label()` | *top_level* | `Mutação / Escrita` | Mescla nós que compartilham um rótulo normalizado, reescrevendo referências de aresta. |
| `disambiguate_file_labels_in_nodes()` | *top_level* | `Mutação / Escrita` | Relabela nós de arquivo com nomes de base colidindo em uma lista bruta de nós, in place. |
| `distinct_repo_tags()` | *top_level* | `Parser / AST / Extração` | Retorna uma tag de repo única e significativa para humanos por grafo de entrada para mesclar-grafos. |
| `edge_data()` | *top_level* | `Leitura / Consulta` | Retorna um dicionário de atributos de uma aresta para (u, v), tolerando MultiGraph. |
| `edge_datas()` | *top_level* | `Leitura / Consulta` | Retorna todos os dicionários de atributos de uma aresta para (u, v); sempre uma lista. |
| `graph_has_legacy_ids()` | *top_level* | `Validação / Segurança` | Se um grafo carregado ainda usa ids de nós pré-#1504 (parent-dir / filename. |
| `prefix_graph_for_global()` | *top_level* | `Mutação / Escrita` | Retorna uma cópia de G com todos os ids de nós prefixados com repo_tag::. |
| `prune_repo_from_graph()` | *top_level* | `Mutação / Escrita` | Remove todos os nós marcados com repo_tag de G in-place. Retorna contagem removida. |

#### Módulo: `graph/cache.py` (1049 LOC)
**Responsabilidade**: Módulo responsável por gerenciar o cache de AST e extrair informações de arquivos Markdown.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_absolutize_source_files_in()` | *top_level* | `Mutação / Escrita` | Inverso de :func:`_relativize_source_files_in`. |
| `_body_content()` | *top_level* | `Parser / AST / Extração` | Remove frontmatter YAML de conteúdo Markdown, retornando apenas o corpo. |
| `_cleanup_stale_ast_entries()` | *top_level* | `Mutação / Escrita` | Remove entradas de cache AST deixadas por outras versões do graphify. |
| `_ensure_stat_index()` | *top_level* | `Leitura / Consulta` | Função não documentada. |
| `_flush_stat_index()` | *top_level* | `Mutação / Escrita` | Função não documentada. |
| `_group_has_partial_marker()` | *top_level* | `Parser / AST / Extração` | True se qualquer nó/aresta/hiperaresta em um grupo por arquivo carregar o marcador interno. |
| `_normalize_path()` | *top_level* | `Parser / AST / Extração` | Normaliza o caminho para chaves de cache consistentes entre diferentes variações de caminho no Windows. |
| `_relativize_source_files_in()` | *top_level* | `Mutação / Escrita` | Altera ``payload`` para reescrever campos ``source_file`` absolutos como relativos. |
| `_resolve_prompt_fp()` | *top_level* | `Parser / AST / Extração` | Fingerprinta o prompt de extração do chamador, ou None quando nenhum é fornecido. |
| `_stat_index_file()` | *top_level* | `Leitura / Consulta` | Função não documentada. |
| `cache_dir()` | *top_level* | `Leitura / Consulta` | Retorna o diretório de cache para ``kind`` - cria se necessário. |
| `cached_files()` | *top_level* | `Leitura / Consulta` | Retorna conjunto de hashes de arquivos que têm uma entrada de cache válida (qualquer tipo). |
| `cached_word_count()` | *top_level* | `Leitura / Consulta` | Contagem de palavras com o mesmo cache de stat-fastpath (tamanho, mtime_ns). |
| `check_semantic_cache()` | *top_level* | `Leitura / Consulta` | Verifica o cache de extração semântica para uma lista de caminhos de arquivo absolutos. |
| `clear_cache()` | *top_level* | `Mutação / Escrita` | Exclui todas as entradas de cache (ast/, semantic/, semantic-deep/, e legado). |
| `file_hash()` | *top_level* | `Parser / AST / Extração` | SHA256 do conteúdo do arquivo + caminho relativo à raiz. |
| `load_cached()` | *top_level* | `Leitura / Consulta` | Retorna extração em cache para este arquivo se o hash corresponder, caso contrário, None. |
| `prompt_fingerprint()` | *top_level* | `Parser / AST / Extração` | Retorna um breve fingerprint estável de um prompt de extração. |
| `prune_semantic_cache()` | *top_level* | `Mutação / Escrita` | Remove entradas de cache semântico órfãs, retornando a contagem removida. |
| `save_cached()` | *top_level* | `Mutação / Escrita` | Salva o resultado da extração em cache para este arquivo. |
| `save_semantic_cache()` | *top_level* | `Mutação / Escrita` | Salva os resultados de extração semântica em cache, indexados por source_file. |

#### Módulo: `graph/callflow_html.py` (2022 LOC)
**Responsabilidade**: Gera HTML de arquitetura de fluxo de chamada a partir de saídas do gráfico conhecimento graphify.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__init__()` | `CallflowOptions` | `Orquestração / Lifecycle` | Inicializa as opções para geração de HTML de arquitetura de fluxo de chamada. |
| `_community_text()` | *top_level* | `Utilitário / Helper` |  |
| `_describe_node()` | *top_level* | `Parser / AST / Extração` | Gerar uma descrição compacta e legível para um nó do gráfico. |
| `_keyword_score()` | *top_level* | `Cálculo / Algoritmo` |  |
| `_node_link_payload()` | *top_level* | `Leitura / Consulta` | Lê o gráfico atual graph.json via analisador de node-link do NetworkX. |
| `_rank_grouped_sections()` | *top_level* | `Cálculo / Algoritmo` | Retornar seções agrupadas selecionadas e comunidades de estouro. |
| `_report_highlights()` | *top_level* | `Leitura / Consulta` | Extrair um cartão de destaque compacto de GRAPH_REPORT.md. |
| `_suggest_tag()` | *top_level* | `Utilitário / Helper` | Sugestão heurística de tag com base no nome do rótulo e tipo de arquivo. |
| `build_community_index()` | *top_level* | `Parser / AST / Extração` | Mapear community_id (str) -> lista de nós. |
| `build_section_node_map()` | *top_level* | `Parser / AST / Extração` | Mapear section_id -> lista de nós pertencentes às suas comunidades. |
| `classify_edges()` | *top_level* | `Parser / AST / Extração` | Classificar arestas como intra-seção ou inter-seção. |
| `derive_flow_chain()` | *top_level* | `Cálculo / Algoritmo` | Derivar uma sequência de fluxo de seção legível a partir de arestas inter-seção. |
| `derive_sections_from_communities()` | *top_level* | `Parser / AST / Extração` | Derivar seções orientadas à arquitetura quando nenhum arquivo JSON de seções é fornecido. |
| `detect_lang()` | *top_level* | `Validação / Segurança` | Resolver idioma automático de rótulos e nomes de nó. |
| `edge_score()` | *top_level* | `Cálculo / Algoritmo` | Classificar arestas por confiança e utilidade para diagramas. |
| `endpoint_id()` | *top_level* | `Parser / AST / Extração` | Normaliza pontos finais de arestas que podem ser strings ou objetos de nó. |
| `first_list()` | *top_level* | `Parser / AST / Extração` | Retorna a primeira lista de um conjunto de locais de esquema possíveis. |
| `first_present()` | *top_level* | `Parser / AST / Extração` | Retorna o primeiro valor não vazio para qualquer chave candidata. |
| `format_node_refs()` | *top_level* | `Parser / AST / Extração` | Renderizar referências de nó como rótulos legíveis em vez de IDs internos. |
| `generate_call_table_rows()` | *top_level* | `Utilitário / Helper` | Gerar scaffolding de linha de tabela de chamada para nós de uma seção. |
| `generate_header()` | *top_level* | `Utilitário / Helper` | Gerar o cabeçalho HTML, título, subtítulo e navegação. |
| `generate_nav()` | *top_level* | `Utilitário / Helper` | Gerar a barra de navegação aderente. |
| `generate_overview_cards()` | *top_level* | `Utilitário / Helper` | Gerar cartões genéricos de visão geral. |
| `generate_overview_graph()` | *top_level* | `Utilitário / Helper` | Gerar uma visão geral de arquitetura de seção legível. |
| `generate_section_cards()` | *top_level* | `Utilitário / Helper` | Gerar cartões de arquivo-chave e notas de design para uma seção. |
| `generate_section_flowchart()` | *top_level* | `Utilitário / Helper` | Gerar um fluxograma de fluxo de chamada compacto e legível para uma seção. |
| `generate_section_intro()` | *top_level* | `Utilitário / Helper` | Gerar o parágrafo introdutório da seção. |
| `group_nodes_by_file()` | *top_level* | `Parser / AST / Extração` | Agrupar nós selecionados por arquivo de origem para subgrafos Mermaid. |
| `html_anchor_id()` | *top_level* | `Utilitário / Helper` | Gerar um ID de âncora HTML estável e único. |
| `html_comment_text()` | *top_level* | `Utilitário / Helper` | Manter comentários HTML gerados bem formados. |
| `humanize_label()` | *top_level* | `Parser / AST / Extração` | Converter rótulos de gráfico em rótulos curtos que as pessoas podem escanear em um diagrama. |
| `infer_project_name()` | *top_level* | `Parser / AST / Extração` | Inferir um nome de projeto de exibição quando os metadados do gráfico não incluem um. |
| `is_zh()` | *top_level* | `Validação / Segurança` | Retornar verdadeiro quando as strings localizadas devem ser chinesas. |
| `label_for_community()` | *top_level* | `Parser / AST / Extração` | Escolher um nome de seção legível para uma comunidade. |
| `load_graph()` | *top_level* | `Leitura / Consulta` | Carrega graph.json. Retorna normalizado (nós, arestas, hiperarestas, metadados). |
| `load_labels()` | *top_level* | `Leitura / Consulta` | Carrega rótulos de comunidade de .graphify_labels.json, tolerando chaves wrapper. |
| `load_report()` | *top_level* | `Leitura / Consulta` | Carrega GRAPH_REPORT.md se existir. |
| `load_sections()` | *top_level* | `Leitura / Consulta` | Carrega definições de seção de arquivo JSON. |
| `main()` | *top_level* | `Orquestração / Lifecycle` | Ponto de entrada principal do módulo. |
| `mermaid_class_defs()` | *top_level* | `Utilitário / Helper` | Estilos nativos Mermaid compartilhados para diagramas legíveis. |
| `mermaid_init()` | *top_level* | `Utilitário / Helper` | Retornar uma diretiva de inicialização Mermaid que dimensiona diagramas usando configuração Mermaid. |
| `mermaid_section_id()` | *top_level* | `Parser / AST / Extração` | Converte um ID de seção (como 'cli-entry') em um ID Mermaid seguro (como 'CLI_ENTRY'). |
| `node_degree_scores()` | *top_level* | `Cálculo / Algoritmo` | Pontuar nós por participação útil de aresta. |
| `node_display_name()` | *top_level* | `Parser / AST / Extração` | Rótulo de nó legível para tabelas e resumos. |
| `node_importance()` | *top_level* | `Parser / AST / Extração` | Usar campos de centralidade do graphify quando disponíveis. |
| `node_in_section()` | *top_level* | `Validação / Segurança` | Verificar se um nó pertence a uma seção. |
| `node_kind()` | *top_level* | `Parser / AST / Extração` | Classificar um nó do gráfico para estilos Mermaid e tags de tabela. |
| `node_label()` | *top_level* | `Parser / AST / Extração` | Construir um rótulo de nó Mermaid legível. |
| `node_mermaid_id()` | *top_level* | `Parser / AST / Extração` | Gera um ID de nó Mermaid seguro a partir de um nó do gráfico. |
| `normalize_communities()` | *top_level* | `Parser / AST / Extração` | Normalizar listas de comunidades de seção de JSON ou strings simples. |
| `normalize_edge()` | *top_level* | `Parser / AST / Extração` | Normaliza arestas do graphify enquanto preserva campos originais. |
| `normalize_node()` | *top_level* | `Parser / AST / Extração` | Normaliza um nó do graphify em variantes comuns do esquema graph.json. |
| `normalize_sections()` | *top_level* | `Parser / AST / Extração` | Garantir que as seções tenham IDs únicos seguros e uma seção de visão geral primeiro. |
| `pick_text()` | *top_level* | `Utilitário / Helper` | Pequeno auxiliar de localização para cópias geradas. |
| `preferred_edges()` | *top_level* | `Cálculo / Algoritmo` | Filtrar para arestas que façam um diagrama de fluxo de chamada legível. |
| `read_json()` | *top_level* | `Leitura / Consulta` | Lê JSON com uma mensagem de erro útil. |
| `relation_label()` | *top_level* | `Parser / AST / Extração` | Mapear nomes de relação de aresta do gráfico para rótulos de diagrama curtos. |
| `resolve_graphify_paths()` | *top_level* | `Parser / AST / Extração` | Resolver diretório raiz do projeto, diretório de saída do graphify e arquivos opcionais. |
| `safe_file_path()` | *top_level* | `Utilitário / Helper` | Retorna um caminho de exibição curto e seguro. |
| `safe_filename()` | *top_level* | `Utilitário / Helper` | Cria um nome de arquivo de stem conservador a partir de um nome de projeto. |
| `safe_mermaid_text()` | *top_level* | `Validação / Segurança` | Sanitiza texto para uso dentro de um rótulo de nó Mermaid. |
| `section_edge_summary()` | *top_level* | `Parser / AST / Extração` | Agregar contagens de aresta inter-seção e nomes de relação. |
| `section_keywords()` | *top_level* | `Parser / AST / Extração` | Escolher palavras representativas de rótulos e nomes de arquivos. |
| `select_diagram_nodes()` | *top_level* | `Cálculo / Algoritmo` | Selecionar um subconjunto compacto e conectado de nós para diagramas legíveis. |
| `should_include_edge()` | *top_level* | `Validação / Segurança` | Decidir se incluir automaticamente uma aresta na saída Mermaid. |
| `stable_ascii_id()` | *top_level* | `Utilitário / Helper` | Constrói um identificador ASCII seguro para Mermaid com um suporte de hash para evitar colisões. |
| `to_float()` | *top_level* | `Parser / AST / Extração` | Converte campos numéricos do gráfico que podem ser serializados como strings. |
| `truncate_text()` | *top_level* | `Utilitário / Helper` | Truncar sem dividir a sintaxe Mermaid. |
| `write_callflow_html()` | *top_level* | `Mutação / Escrita` | Gerar HTML de arquitetura de fluxo de chamada a partir de arquivos de saída do graphify. |

#### Módulo: `graph/cluster.py` (402 LOC)
**Responsabilidade**: Módulo responsável por detectar comunidades em grafos NetworkX usando algoritmos como Leiden e Louvain.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_dominant_source_stem()` | *top_level* | `Parser / AST / Extração` | Nome de arquivo raiz compartilhado por maioria dos *membros*, ou "" quando eles não compartilham nenhum. |
| `_is_identifier_label()` | *top_level* | `Parser / AST / Extração` | Se um rótulo de nó lê-se como um nome de símbolo em vez de prosa. |
| `_partition()` | *top_level* | `Cálculo / Algoritmo` | Executa detecção de comunidade. Retorna {node_id: community_id}. |
| `_short_discriminator()` | *top_level* | `Parser / AST / Extração` | Alguns palavras do membro mais denso, para distinguir comunidades do mesmo arquivo. |
| `_split_community()` | *top_level* | `Cálculo / Algoritmo` | Executa uma segunda passagem de Leiden em um subgrafo de comunidade para dividi-lo ainda mais. |
| `_suppress_output()` | *top_level* | `Utilitário / Helper` | Gerenciador de contexto para suprimir stdout/stderr durante chamadas de biblioteca. |
| `cluster()` | *top_level* | `Cálculo / Algoritmo` | Executa detecção de comunidade Leiden. Retorna {community_id: [node_ids]}. |
| `cohesion_score()` | *top_level* | `Cálculo / Algoritmo` | Taxa de arestas intra-comunidade reais para o máximo possível. |
| `community_member_sigs()` | *top_level* | `Cálculo / Algoritmo` | Assinaturas de membro por comunidade: {cid: sha256(sorted member ids)}. |
| `label_communities_by_hub()` | *top_level* | `Cálculo / Algoritmo` | Rótulos de comunidade determinísticos, sem LLM: nomeia cada comunidade após seu hub. |
| `remap_communities_to_previous()` | *top_level* | `Cálculo / Algoritmo` | Reatribui IDs de comunidade para maximizar a sobreposição com uma atribuição anterior. |
| `score_all()` | *top_level* | `Cálculo / Algoritmo` | Função não documentada. |

#### Módulo: `graph/dedup.py` (762 LOC)
**Responsabilidade**: Pipeline para deduplicação de entidades em gráficos de conhecimento, incluindo funções de normalização, shingling, minhash e resolução de conflitos.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__init__()` | `_UF` | `Orquestração / Lifecycle` | Inicializa a estrutura de união-find. |
| `components()` | `_UF` | `Leitura / Consulta` | Retorna os componentes conectados. |
| `find()` | `_UF` | `Leitura / Consulta` | Encontra o conjunto ao qual um elemento pertence. |
| `union()` | `_UF` | `Mutação / Escrita` | Une dois conjuntos. |
| `_collision_rank()` | *top_level* | `Cálculo / Algoritmo` | Define uma ordem total para escolher o sobrevivente de um conflito de ID. |
| `_crossfile_fileanchored_blocked()` | *top_level* | `Validação / Segurança` | Bloqueia a fusão de nós ancorados em arquivos entre arquivos. |
| `_defines_id()` | *top_level* | `Validação / Segurança` | Verifica se o arquivo de origem da entidade é o arquivo que seu ID codifica. |
| `_entropy()` | *top_level* | `Cálculo / Algoritmo` | Calcula a entropia de Shannon do texto normalizado. |
| `_id_prefixes()` | *top_level* | `Parser / AST / Extração` | Retorna os prefixos de ID que uma entidade pode gerar. |
| `_is_code()` | *top_level* | `Parser / AST / Extração` | Verifica se uma entidade é um símbolo de código extraído da AST. |
| `_is_variant_pair()` | *top_level* | `Validação / Segurança` | Verifica se duas entidades são variantes de modelo/SKU. |
| `_llm_tiebreak()` | *top_level* | `Orquestração / Lifecycle` | Resolve pares ambíguos em lote via LLM. |
| `_make_minhash()` | *top_level* | `Cálculo / Algoritmo` | Cria uma função minhash. |
| `_merge_missing_attributes()` | *top_level* | `Mutação / Escrita` | Preenche os atributos ausentes do sobrevivente com os atributos da duplicata. |
| `_norm()` | *top_level* | `Parser / AST / Extração` | Normaliza o texto para minúsculas e colapsa sequências não alfanuméricas. |
| `_numeric_tokens_differ()` | *top_level* | `Validação / Segurança` | Verifica se duas entidades têm números incorporados diferentes. |
| `_pick_winner()` | *top_level* | `Orquestração / Lifecycle` | Escolhe o sobrevivente canônico: sem suporte de chunk, depois ID mais curto, depois o ID. |
| `_report_id_collision()` | *top_level* | `Utilitário / Helper` | Relata um conflito de ID proporcional ao custo de descartar o perdedor. |
| `_same_source_entity()` | *top_level* | `Validação / Segurança` | Verifica se duas entidades exatamente identificadas vieram do mesmo arquivo de origem. |
| `_shingles()` | *top_level* | `Parser / AST / Extração` | Gera shingles (k-gramas) do texto. |
| `_short_label_blocked()` | *top_level* | `Validação / Segurança` | Bloqueia a fusão fuzzy de rótulos curtos a menos que sejam substituições de caractere únicos. |
| `deduplicate_entities()` | *top_level* | `Orquestração / Lifecycle` | Deduplica entidades semelhantes em um gráfico de conhecimento. |

#### Módulo: `graph/detect.py` (1821 LOC)
**Responsabilidade**: Este módulo contém funções para classificar e detectar arquivos, extrair texto de diferentes formatos e gerenciar manifestos de arquivos.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_auto_follow_symlinks()` | *top_level* | `Leitura / Consulta` | Verifica se ``root`` tem qualquer filho simbólico direto. |
| `_env_command_args()` | *top_level* | `Parser / AST / Extração` | Remove opções e atribuições de variáveis de `env(1)` do comando, retornando o restante. |
| `_file_within_size_cap()` | *top_level* | `Validação / Segurança` | Verifica se o tamanho do arquivo está dentro de uma capacidade especificada. |
| `_find_vcs_root()` | *top_level* | `Leitura / Consulta` | Percorre para cima do diretório de início; retorna o primeiro diretório contendo um marcador VCS. |
| `_generic_keyword_hit()` | *top_level* | `Validação / Segurança` | Verifica se uma palavra-chave genérica de segredo aparece no nome do arquivo. |
| `_git_info_exclude()` | *top_level* | `Leitura / Consulta` | Resolve ``$GIT_DIR/info/exclude`` para o repositório raiz em ``vcs_root``. |
| `_has_venv_markers()` | *top_level* | `Leitura / Consulta` | Verifica se um diretório tem estrutura de virtualenv/conda no disco. |
| `_is_graphable_source()` | *top_level* | `Leitura / Consulta` | Verifica se um arquivo é uma fonte de linguagem de programação genuína. |
| `_is_ignored()` | *top_level* | `Validação / Segurança` | Verifica se o caminho deve ser ignorado de acordo com os padrões .graphifyignore. |
| `_is_noise_dir()` | *top_level* | `Leitura / Consulta` | Verifica se um nome de diretório parece um venv, cache ou diretório de dependência. |
| `_is_prose_note()` | *top_level* | `Leitura / Consulta` | Verifica se um arquivo é uma nota/prosa com um slug de tópico multi-palavras. |
| `_is_sensitive()` | *top_level* | `Validação / Segurança` | Verifica se um arquivo provavelmente contém segredos e deve ser ignorado. |
| `_load_dir_own_ignore()` | *top_level* | `Leitura / Consulta` | Lê .gitignore/.graphifyignore diretamente dentro de *d* (não seus ancestrais). |
| `_load_graphifyignore()` | *top_level* | `Leitura / Consulta` | Lê arquivos .graphifyignore e retorna pares (diretório âncora, padrão). |
| `_looks_like_paper()` | *top_level* | `Leitura / Consulta` | Heurística: verifica se um arquivo de texto parece um artigo acadêmico. |
| `_match_anchored_ignore_pattern()` | *top_level* | `Validação / Segurança` | Corresponde a um padrão gitignore âncorado sem permitir que ``*`` cruze ``/``. |
| `_md5_file()` | *top_level* | `Utilitário / Helper` | MD5 dos conteúdos do arquivo transmitidos em blocos de 64KB - apenas para detecção de alterações. |
| `_os_path()` | *top_level* | `Utilitário / Helper` | Retorna uma string de caminho do sistema operacional segura para open()/stat() em caminhos longos do Windows. |
| `_parse_gitignore_line()` | *top_level* | `Parser / AST / Extração` | Parseia uma linha bruta de um arquivo .graphifyignore de acordo com a especificação gitignore. |
| `_resolves_under_root()` | *top_level* | `Leitura / Consulta` | Verifica se ``path`` resolve para um destino dentro de ``root``. |
| `_shebang_file_type()` | *top_level* | `Parser / AST / Extração` | Verifica a primeira linha de um arquivo sem extensão para uma linha shebang. |
| `_shebang_interpreter()` | *top_level* | `Parser / AST / Extração` | Retorna o nome do interpretador de uma linha shebang. |
| `_split_env_s()` | *top_level* | `Parser / AST / Extração` | Re-tokeniza um comando empacotado com `env -S`/`--split-string`, adicionando o prefixo. |
| `_stat_and_hash()` | *top_level* | `Utilitário / Helper` | Stat + MD5 de um único arquivo; retorna None em caso de OSError (por exemplo, excluído durante a execução). |
| `_to_absolute_from_storage()` | *top_level* | `Utilitário / Helper` | Inverso de :func:`_to_relative_for_storage`. |
| `_to_relative_for_storage()` | *top_level* | `Utilitário / Helper` | Retorna ``key`` como um caminho relativo para frente da ``root``. |
| `_zip_within_caps()` | *top_level* | `Validação / Segurança` | Rejeita arquivos de office baseados em zip que possam ser uma bomba de zip/XML. |
| `classify_file()` | *top_level* | `Leitura / Consulta` | Classifica um arquivo com base em vários critérios. |
| `convert_office_file()` | *top_level* | `Mutação / Escrita` | Converte um arquivo .docx ou .xlsx para um sidecar markdown no out_dir. |
| `count_words()` | *top_level* | `Cálculo / Algoritmo` | Conta o número de palavras em um arquivo. |
| `detect()` | *top_level* | `Leitura / Consulta` | Detecta arquivos com base em vários critérios. |
| `detect_incremental()` | *top_level* | `Leitura / Consulta` | Como detect(), mas retorna apenas novos ou arquivos modificados desde a última execução. |
| `docx_to_markdown()` | *top_level* | `Leitura / Consulta` | Converte um arquivo .docx para texto markdown usando python-docx. |
| `extract_pdf_text()` | *top_level* | `Leitura / Consulta` | Extrai texto simples de um arquivo PDF usando pypdf. |
| `load_manifest()` | *top_level* | `Leitura / Consulta` | Carrega o manifesto de uma execução anterior. Retorna {} em qualquer erro. |
| `save_manifest()` | *top_level* | `Mutação / Escrita` | Salva os mtimes atuais e hashes de conteúdo dos arquivos para detecção de alterações. |
| `xlsx_extract_structure()` | *top_level* | `Leitura / Consulta` | Extrai nós estruturais (planilhas, tabelas nomeadas, cabeçalhos de coluna) de um arquivo .xlsx. |
| `xlsx_to_markdown()` | *top_level* | `Leitura / Consulta` | Converte um arquivo .xlsx para texto markdown usando openpyxl. |

#### Módulo: `graph/export.py` (1094 LOC)
**Responsabilidade**: Módulo responsável por exportar e manipular gráficos em diferentes formatos, incluindo Obsidian, Canvas, GraphML e SVG.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_cap_filename()` | *top_level* | `Utilitário / Helper` | Limita o comprimento do nome do arquivo para permanecer abaixo de 255 bytes. |
| `_cypher_escape()` | *top_level* | `Parser / AST / Extração` | Escapa uma string para uma inserção segura em um literal Cypher simplesmente citado. |
| `_cypher_label()` | *top_level* | `Parser / AST / Extração` | Sanitiza um valor usado em uma posição de identificador (rótulo de nó / tipo de relação). |
| `_dedup_node_filenames()` | *top_level* | `Utilitário / Helper` | Mapeia cada node_id para um nome de arquivo de nota único, anexando um suporte numérico. |
| `_git_head()` | *top_level* | `Utilitário / Helper` | Retorna o hash do commit HEAD atual do git, ou None se não estiver em um repositório git. |
| `_obsidian_tag()` | *top_level* | `Utilitário / Helper` | Sanitiza um nome de comunidade para uso como uma tag do Obsidian. |
| `_strip_diacritics()` | *top_level* | `Utilitário / Helper` | Remove acentos de uma string. |
| `_yaml_str()` | *top_level* | `Parser / AST / Extração` | Escapa um valor para uma inserção segura em um escalar YAML duplamente citado. |
| `attach_hyperedges()` | *top_level* | `Mutação / Escrita` | Armazena hiperarestas no dicionário de metadados do gráfico. |
| `backup_if_protected()` | *top_level* | `Utilitário / Helper` | Realiza um snapshot dos artefatos do gráfico em uma subpasta datada antes de uma sobrescrita. |
| `existing_graph_node_count()` | *top_level* | `Leitura / Consulta` | Retorna a contagem de nós de um gráfico existente graph.json. |
| `prune_dangling_edges()` | *top_level* | `Mutação / Escrita` | Remove arestas cujo nó de origem ou destino não está no conjunto de nós. |
| `to_canvas()` | *top_level* | `Exportação` | Exporta o gráfico como um arquivo do Obsidian Canvas - comunidades como grupos, nós como cartões. |
| `to_cypher()` | *top_level* | `Exportação` | Exporta o gráfico para formato Cypher. |
| `to_graphml()` | *top_level* | `Exportação` | Exporta o gráfico como GraphML - abre em Gephi, yEd e qualquer ferramenta compatível com GraphML. |
| `to_json()` | *top_level* | `Exportação` | Exporta o gráfico para formato JSON. |
| `to_obsidian()` | *top_level* | `Exportação` | Exporta o gráfico como um cofre do Obsidian - um arquivo .md por nó com [[wikilinks]]. |
| `to_svg()` | *top_level* | `Exportação` | Exporta o gráfico como um arquivo SVG usando matplotlib + layout de primavera. |

#### Módulo: `graph/exporters/__init__.py` (1 LOC)
**Responsabilidade**: Pacote de exportadores.

*Módulo de constantes, tipos ou declarações puras sem funções executáveis.*

#### Módulo: `graph/exporters/base.py` (14 LOC)
**Responsabilidade**: Constantes e ajudantes compartilhados para o pacote de exportadores do gráfico.

*Módulo de constantes, tipos ou declarações puras sem funções executáveis.*

#### Módulo: `graph/exporters/graphdb.py` (173 LOC)
**Responsabilidade**: Módulo responsável por exportar o gráfico para bancos de dados como Neo4j e FalkorDB.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `push_to_falkordb()` | *top_level* | `Exportação` | Empurra o gráfico diretamente para uma instância FalkorDB em execução via o SDK Python. |
| `push_to_neo4j()` | *top_level* | `Exportação` | Empurra o gráfico diretamente para uma instância Neo4j em execução via o driver Python. |

#### Módulo: `graph/exporters/html.py` (560 LOC)
**Responsabilidade**: Módulo responsável por exportar o gráfico como uma visualização HTML interativa.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_html_script()` | *top_level* | `Utilitário / Helper` | Define um script HTML. |
| `_html_styles()` | *top_level* | `Utilitário / Helper` | Define estilos HTML. |
| `_hyperedge_script()` | *top_level* | `Utilitário / Helper` | Define um script para hiperarestas. |
| `_viz_node_limit()` | *top_level* | `Utilitário / Helper` | Retorna o limite efetivo de nós de visualização, respeitando a variável de ambiente GRAPHIFY_VIZ_NODE_LIMIT. |
| `to_html()` | *top_level* | `Exportação` | Gera uma visualização interativa vis.js HTML do gráfico. |

#### Módulo: `graph/extract.py` (5395 LOC)
**Responsabilidade**: Deterministic structural extraction from source code using tree-sitter. Outputs nodes+edges dicts.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_augment_js_reexport_edges()` | *top_level* | `Parser / AST / Extração` | Augment JavaScript reexport edges. |
| `_canonicalize_csharp_namespace_nodes()` | *top_level* | `Parser / AST / Extração` | Collapse duplicate C# namespace nodes. |
| `_check_tree_sitter_version()` | *top_level* | `Validação / Segurança` | Check if the tree-sitter version is compatible. |
| `_extract_js_rationale()` | *top_level* | `Parser / AST / Extração` | Extract rationale comments and doc references from JavaScript source. |
| `_extract_parallel()` | *top_level* | `Orquestração / Lifecycle` | Extract data from multiple files in parallel. |
| `_extract_python_rationale()` | *top_level* | `Parser / AST / Extração` | Extract rationale comments and docstrings from Python source. |
| `_extract_sequential()` | *top_level* | `Orquestração / Lifecycle` | Extract data from multiple files sequentially. |
| `_extract_single_file()` | *top_level* | `Orquestração / Lifecycle` | Extract data from a single file in a subprocess. |
| `_extract_spock_fallback()` | *top_level* | `Parser / AST / Extração` | Extract data from Spock spec files using regex. |
| `_file_node_id()` | *top_level* | `Parser / AST / Extração` | Generate a unique file-level node ID. |
| `_get_c_func_name()` | *top_level* | `Parser / AST / Extração` | Extract function names from C source code. |
| `_get_extractor()` | *top_level* | `Orquestração / Lifecycle` | Get the correct extractor function for a file. |
| `_import_c()` | *top_level* | `Parser / AST / Extração` | Extract imports from C source code. |
| `_import_csharp()` | *top_level* | `Parser / AST / Extração` | Extract imports from C# source code. |
| `_import_java()` | *top_level* | `Parser / AST / Extração` | Extract imports from Java source code. |
| `_import_js()` | *top_level* | `Parser / AST / Extração` | Extract imports from JavaScript source code. |
| `_import_kotlin()` | *top_level* | `Parser / AST / Extração` | Extract imports from Kotlin source code. |
| `_import_lua()` | *top_level* | `Parser / AST / Extração` | Extract imports from Lua source code. |
| `_import_php()` | *top_level* | `Parser / AST / Extração` | Extract imports from PHP source code. |
| `_import_python()` | *top_level* | `Parser / AST / Extração` | Extract imports from Python source code. |
| `_import_scala()` | *top_level* | `Parser / AST / Extração` | Extract imports from Scala source code. |
| `_import_swift()` | *top_level* | `Parser / AST / Extração` | Extract imports from Swift source code. |
| `_is_autogenerated_python()` | *top_level* | `Validação / Segurança` | Determine if a Python file is auto-generated. |
| `_is_cpp_header()` | *top_level* | `Validação / Segurança` | Determine if a file is a C++ header. |
| `_is_objc_header()` | *top_level* | `Validação / Segurança` | Determine if a file is an Objective-C header. |
| `_is_objc_source()` | *top_level* | `Validação / Segurança` | Determine if a file is an Objective-C source. |
| `_is_spock_file()` | *top_level* | `Validação / Segurança` | Determine if a file contains Spock-style methods. |
| `_is_top_level_function_definition()` | *top_level* | `Validação / Segurança` | Determine if a function is a top-level definition. |
| `_lang_family()` | *top_level* | `Validação / Segurança` | Determine the interop family of a language. |
| `_lang_is_case_insensitive()` | *top_level* | `Validação / Segurança` | Determine if a language resolves identifiers case-insensitively. |
| `_merge_swift_extensions()` | *top_level* | `Parser / AST / Extração` | Merge Swift extension nodes. |
| `_node_label_key()` | *top_level* | `Utilitário / Helper` | Get the key for node labels. |
| `_project_xml_is_safe()` | *top_level* | `Validação / Segurança` | Validate XML project files for safety. |
| `_raise_recursion_limit()` | *top_level* | `Utilitário / Helper` | Increase the recursion limit to handle deep parsing. |
| `_repoint_python_package_imports()` | *top_level* | `Parser / AST / Extração` | Repoint Python absolute-import edges to the real file node. |
| `_resolve_cpp_member_calls()` | *top_level* | `Parser / AST / Extração` | Resolve C++ member calls. |
| `_resolve_csharp_member_calls()` | *top_level* | `Parser / AST / Extração` | Resolve C# member calls. |
| `_resolve_java_member_calls()` | *top_level* | `Parser / AST / Extração` | Resolve Java member calls. |
| `_resolve_name()` | *top_level* | `Parser / AST / Extração` | Resolve the name from a node using configuration settings. |
| `_resolve_objc_member_calls()` | *top_level* | `Parser / AST / Extração` | Resolve Objective-C message sends. |
| `_resolve_python_member_calls()` | *top_level* | `Parser / AST / Extração` | Resolve Python member calls. |
| `_resolve_swift_member_calls()` | *top_level* | `Parser / AST / Extração` | Resolve Swift member calls. |
| `_resolve_typescript_member_calls()` | *top_level* | `Parser / AST / Extração` | Resolve TypeScript member calls. |
| `_rewire_unique_stub_nodes()` | *top_level* | `Parser / AST / Extração` | Map unresolved stub nodes to unique real definitions. |
| `_safe_extract()` | *top_level* | `Parser / AST / Extração` | Safely extract data from source code. |
| `_safe_extract_with_xaml_root()` | *top_level* | `Parser / AST / Extração` | Safely extract data with XAML root. |
| `_xaml_binding_refs()` | *top_level* | `Utilitário / Helper` | Extract binding references in XAML. |
| `_xaml_codebehind_path()` | *top_level* | `Utilitário / Helper` | Get the path to the code-behind file in XAML. |
| `_xaml_codebehind_symbols()` | *top_level* | `Utilitário / Helper` | Extract symbols from the code-behind file in XAML. |
| `_xaml_communitytoolkit_members()` | *top_level* | `Utilitário / Helper` | Handle Community Toolkit members in XAML. |
| `_xaml_csharp_class_nodes()` | *top_level* | `Utilitário / Helper` | Get C# class nodes in XAML. |
| `_xaml_explicit_viewmodel_names()` | *top_level* | `Utilitário / Helper` | Get explicit view model names in XAML. |
| `_xaml_inferred_viewmodel_names()` | *top_level* | `Utilitário / Helper` | Infer view model names in XAML. |
| `_xaml_markup_extension()` | *top_level* | `Utilitário / Helper` | Handle XAML markup extensions. |
| `_xaml_pascal_name()` | *top_level* | `Utilitário / Helper` | Convert to Pascal case in XAML. |
| `_xaml_prism_autowire_viewmodel()` | *top_level* | `Utilitário / Helper` | Handle Prism auto-wiring in XAML. |
| `_xaml_project_root()` | *top_level* | `Utilitário / Helper` | Get the root of the XAML project. |
| `_xaml_split_markup_args()` | *top_level* | `Utilitário / Helper` | Split markup arguments in XAML. |
| `_xaml_static_resource_key()` | *top_level* | `Utilitário / Helper` | Get the key for XAML static resources. |
| `_xaml_type_simple_name()` | *top_level* | `Utilitário / Helper` | Get the simple name of a XAML type. |
| `_xml_local_name()` | *top_level* | `Utilitário / Helper` | Get the local name of an XML element. |
| `collect_files()` | *top_level* | `Orquestração / Lifecycle` | Collect files for extraction. |
| `extract()` | *top_level* | `Parser / AST / Extração` | Extract data from a list of code files. |
| `extract_astro()` | *top_level* | `Parser / AST / Extração` | Extract imports from Astro source code. |
| `extract_c()` | *top_level* | `Parser / AST / Extração` | Extract functions and includes from C source code. |
| `extract_cpp()` | *top_level* | `Parser / AST / Extração` | Extract functions, classes, and includes from C++ source code. |
| `extract_csharp()` | *top_level* | `Parser / AST / Extração` | Extract classes, methods, and imports from C# source code. |
| `extract_csproj()` | *top_level* | `Parser / AST / Extração` | Extract packages and project references from .csproj files. |
| `extract_groovy()` | *top_level* | `Parser / AST / Extração` | Extract classes, methods, and imports from Groovy source code. |
| `extract_java()` | *top_level* | `Parser / AST / Extração` | Extract classes, methods, and imports from Java source code. |
| `extract_js()` | *top_level* | `Parser / AST / Extração` | Extract classes, functions, and imports from JavaScript source code. |
| `extract_kotlin()` | *top_level* | `Parser / AST / Extração` | Extract classes, methods, and imports from Kotlin source code. |
| `extract_lazarus_package()` | *top_level* | `Parser / AST / Extração` | Extract package metadata from Lazarus package files. |
| `extract_lua()` | *top_level* | `Parser / AST / Extração` | Extract functions, methods, and calls from Lua source code. |
| `extract_php()` | *top_level* | `Parser / AST / Extração` | Extract classes, methods, and calls from PHP source code. |
| `extract_python()` | *top_level* | `Parser / AST / Extração` | Extract classes, functions, and imports from Python source code. |
| `extract_ruby()` | *top_level* | `Parser / AST / Extração` | Extract classes, methods, and calls from Ruby source code. |
| `extract_scala()` | *top_level* | `Parser / AST / Extração` | Extract classes, methods, and imports from Scala source code. |
| `extract_slnx()` | *top_level* | `Parser / AST / Extração` | Extract projects and dependencies from .slnx files. |
| `extract_svelte()` | *top_level* | `Parser / AST / Extração` | Extract imports from Svelte source code. |
| `extract_swift()` | *top_level* | `Parser / AST / Extração` | Extract classes, methods, and imports from Swift source code. |
| `extract_vue()` | *top_level* | `Parser / AST / Extração` | Extract imports from Vue source code. |
| `extract_xaml()` | *top_level* | `Parser / AST / Extração` | Extract XAML structure, bindings, and event handlers. |

#### Módulo: `graph/extractors/__init__.py` (64 LOC)
**Responsabilidade**: Per-language extractors, incrementally migrated out of graphify/extract.py.

*Módulo de constantes, tipos ou declarações puras sem funções executáveis.*

#### Módulo: `graph/extractors/apex.py` (215 LOC)
**Responsabilidade**: Apex extractor. Moved verbatim from graphify/extract.py.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_apex()` | *top_level* | `Parser / AST / Extração` | Extract classes, interfaces, enums, methods, and Salesforce constructs from Apex code. |

#### Módulo: `graph/extractors/base.py` (75 LOC)
**Responsabilidade**: Base functions for extractors.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_file_stem()` | *top_level* | `Utilitário / Helper` | Stem used as the node-ID prefix for a file and its symbols. |
| `_make_id()` | *top_level* | `Utilitário / Helper` | Generate a unique identifier. |
| `_read_text()` | *top_level* | `Utilitário / Helper` | Read text content from a file. |

#### Módulo: `graph/extractors/bash.py` (248 LOC)
**Responsabilidade**: Bash extractor. Moved verbatim from graphify/extract.py.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_bash()` | *top_level* | `Parser / AST / Extração` | Extract functions, source imports, and cross-function calls from a .sh file. |

#### Módulo: `graph/extractors/blade.py` (53 LOC)
**Responsabilidade**: Laravel Blade template extractor. Moved verbatim from graphify/extract.py.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_blade()` | *top_level* | `Parser / AST / Extração` | Extract @include, <livewire:> components, and wire:click bindings from Blade templates. |

#### Módulo: `graph/extractors/csharp.py` (393 LOC)
**Responsabilidade**: Módulo responsável pela extração e resolução de tipos e referências em código C#.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_build_csharp_type_def_index()` | *top_level* | `Parser / AST / Extração` | Retorna um índice determinístico de definições de tipos C#. |
| `_resolve_cross_file_csharp_imports()` | *top_level* | `Parser / AST / Extração` | Reaponta importações C# resolvíveis para nós internos canônicos. |
| `_resolve_csharp_type_references()` | *top_level* | `Parser / AST / Extração` | Arbitra todos os alvos de herança, implementação e referência de tipos C#. |
| `_strip_trailing_csharp_generic_args()` | *top_level* | `Parser / AST / Extração` | Remove argumentos genéricos trailing de tipos C#. |

#### Módulo: `graph/extractors/dart.py` (528 LOC)
**Responsabilidade**: Módulo responsável pela extração de elementos de código Dart.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_dart()` | *top_level* | `Parser / AST / Extração` | Extrai classes, mixins, funções, imports, chamadas genéricas e anotações de um arquivo .dart usando regex. |

#### Módulo: `graph/extractors/dm.py` (494 LOC)
**Responsabilidade**: Módulo responsável pela extração de elementos de código DM, DMI, DMM e DMF.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_dmm_type_path()` | *top_level* | `Parser / AST / Extração` | Obtém o caminho de tipo de um tile .dmm. |
| `_read_dmi_description()` | *top_level* | `Parser / AST / Extração` | Extrai o texto de metadados BYOND de um arquivo .dmi PNG ou retorna uma string vazia em caso de falha. |
| `_split_dmm_tile()` | *top_level* | `Parser / AST / Extração` | Divide um tile .dmm. |
| `extract_dm()` | *top_level* | `Parser / AST / Extração` | Extrai tipos, procedimentos, inclusões e chamadas de um arquivo .dm/.dme. |
| `extract_dmf()` | *top_level* | `Parser / AST / Extração` | Extrai janelas e controles de um arquivo .dmf interface. |
| `extract_dmi()` | *top_level* | `Parser / AST / Extração` | Extrai nomes de estados de ícone de um arquivo .dmi (folha de ícones PNG BYOND). |
| `extract_dmm()` | *top_level* | `Parser / AST / Extração` | Extrai referências de caminho de tipo do dicionário de tiles de um arquivo .dmm. |

#### Módulo: `graph/extractors/elixir.py` (228 LOC)
**Responsabilidade**: Módulo responsável pela extração de elementos de código Elixir.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_elixir()` | *top_level* | `Parser / AST / Extração` | Extrai módulos, funções, imports e chamadas de um arquivo .ex/.exs. |

#### Módulo: `graph/extractors/engine.py` (4595 LOC)
**Responsabilidade**: engine — moved verbatim from graphify/extract.py.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_c_collect_type_refs()` | *top_level* | `Type Extraction` | Walk a C type expression and append (name, role) tuples for user-defined types. |
| `_cpp_collect_type_refs()` | *top_level* | `Type Extraction` | Walk a C++ type expression and append (name, role) tuples. |
| `_cpp_declarator_name()` | *top_level* | `Name Extraction` | Returns the bare variable name from a C++ declaration declarator, unwrapping. |
| `_cpp_local_var_types()` | *top_level* | `Type Collection` | Collects ``var -> ClassName`` from local variable declarations in a C++. |
| `_csharp_attribute_names()` | *top_level* | `Attribute Analysis` | Collects attribute names from C# declarations. |
| `_csharp_classify_base()` | *top_level* | `Inheritance Analysis` | Classifies base relationships in C# code. |
| `_csharp_collect_type_refs()` | *top_level* | `Type Analysis` | Collects type references in C# code. |
| `_csharp_extra_walk()` | *top_level* | `Node Handling` | Handles namespace declarations for C#. Returns True if handled. |
| `_csharp_member_type_table()` | *top_level* | `Type Collection` | Collects ``name -> TypeName`` for C# receiver typing (#1609): class fields. |
| `_csharp_namespace_id()` | *top_level* | `Utility` | Extracts the namespace ID from C# code. |
| `_csharp_namespace_name()` | *top_level* | `Name Extraction` |  |
| `_csharp_pre_scan_interfaces()` | *top_level* | `Interface Analysis` | Scans for interfaces declared in C# code. |
| `_csharp_type_parameters_in_scope()` | *top_level* | `Type Parameter Analysis` | Identifies type parameters in scope for C# code. |
| `_dynamic_import_js()` | *top_level* | `Import Detection` | Detects dynamic import() calls in JS/TS and emits imports_from edges. |
| `_extract_generic()` | *top_level* | `Generic AST Extractor` | Extracts generic AST nodes based on LanguageConfig. |
| `_find_body()` | *top_level* | `Node Search` | Finds the body node using config.body_field, falling back to child types. |
| `_find_require_call()` | *top_level* | `Call Detection` | Returns the call_expression node if `value_node` is a `require(...)` call. |
| `_get_cpp_func_name()` | *top_level* | `Name Extraction` | Recursively unwraps declarator to find the innermost identifier (C++). |
| `_java_annotation_names()` | *top_level* | `Annotation Analysis` | Collects annotation names from Java declarations. |
| `_java_collect_type_refs()` | *top_level* | `Type Analysis` | Collects type references in Java code. |
| `_java_declarator_names()` | *top_level* | `Declarator Analysis` | Collects declarator names in Java code. |
| `_java_extra_walk()` | *top_level* | `Language Specific Handler` | Handles enum_constant for Java and returns True if handled. |
| `_java_lambda_parameters()` | *top_level* | `Lambda Analysis` | Analyzes lambda parameters in Java code. |
| `_java_method_receiver_types()` | *top_level* | `Receiver Analysis` | Builds the receiver type table for Java methods. |
| `_java_receiver_type_name()` | *top_level* | `Receiver Analysis` | Determines the receiver type name in Java code. |
| `_java_type_parameters_in_scope()` | *top_level* | `Type Parameter Analysis` | Identifies type parameters in scope for Java code. |
| `_js_collect_pattern_idents()` | *top_level* | `Identifier Collection` | Collects binding identifier names from a JS/TS pattern. |
| `_js_dispatch_value_idents()` | *top_level* | `Identifier Collection` | Yields identifier value-nodes of a JS/TS object/array literal that are. |
| `_js_extra_walk()` | *top_level* | `Node Handling` | Handles lexical_declaration (arrow functions, CJS requires, module-level const literals) for JS/TS. Returns True if handled. |
| `_js_local_bound_names()` | *top_level* | `Name Binding` | Names bound locally inside a JS/TS function: parameters plus `const`/`let`/`var`. |
| `_js_member_assignment_target()` | *top_level* | `Assignment Classification` | Classifies the symbol an `assignment_expression` LHS defines when its RHS. |
| `_js_module_bound_names()` | *top_level* | `Name Binding` | Module-scope names rebound to NON-function data (`const X = {...}`, `let y = 5`). |
| `_kotlin_collect_type_refs()` | *top_level* | `Type Extraction` | Walk a Kotlin type expression and append (name, role) tuples. |
| `_kotlin_extra_walk()` | *top_level* | `Language Specific Handler` | Handles enum_entry for Kotlin and returns True if handled. |
| `_kotlin_function_return_type_node()` | *top_level* | `Type Extraction` | Find the return-type node of a Kotlin function_declaration. |
| `_kotlin_property_type_node()` | *top_level* | `Type Extraction` | Find the user_type node within a Kotlin property_declaration. |
| `_kotlin_user_type_name()` | *top_level* | `Type Analysis` | Extracts the head identifier text from Kotlin user types. |
| `_php_collect_type_refs()` | *top_level* | `Type Analysis` | Collects type references in PHP code. |
| `_php_method_return_type_node()` | *top_level* | `Return Type Analysis` | Identifies the return type node in PHP methods. |
| `_php_name_text()` | *top_level* | `Name Analysis` | Extracts unqualified name text from PHP code. |
| `_python_collect_assignment_targets()` | *top_level* | `Name Extraction` | Identifiers bound as `pattern` targets under a Python AST subtree. |
| `_python_collect_param_refs()` | *top_level* | `Parameter Extraction` | Collect type refs from each typed parameter under a `parameters` node. |
| `_python_collect_type_refs()` | *top_level* | `Type Analysis` | Collects type references in Python code. |
| `_python_local_bound_names()` | *top_level* | `Name Extraction` | Names bound LOCALLY inside a Python function: parameters plus assignment. |
| `_python_module_bound_names()` | *top_level* | `Name Extraction` | Names rebound by assignment at MODULE scope. |
| `_python_param_names()` | *top_level* | `Name Extraction` | Return plain parameter identifiers declared on a Python `parameters` node. |
| `_read_csharp_type_name()` | *top_level* | `Type Resolver` | Resolves a C# type name, including its qualifier prefix. |
| `_require_imports_js()` | *top_level* | `Import Detection` | Detects CommonJS require imports inside lexical_declaration / variable_declaration. |
| `_ruby_const_last_name()` | *top_level* | `Constant Name Extractor` | Extracts the last constant name from a constant or scope resolution. |
| `_ruby_extra_walk()` | *top_level* | `Language Specific Handler` | Handles Ruby constant assignments with RHS as Struct.new(...). |
| `_ruby_local_class_bindings()` | *top_level* | `Local Class Binding Mapper` | Maps local variables to their respective class names within a Ruby scope. |
| `_ruby_new_class_name()` | *top_level* | `Class Name Extractor` | Returns the class name if the node is a ClassName.new(...) call. |
| `_scala_collect_type_refs()` | *top_level* | `Type Extraction` | Walk a Scala type expression and append (name, role) tuples. |
| `_semantic_reference_edge()` | *top_level* | `Utility` | Identifies semantic reference edges in the code. |
| `_source_location()` | *top_level* | `Utility` | Determines the source location of a code element. |
| `_swift_classify_base()` | *top_level* | `Classification` | Classify a Swift inheritance_specifier entry as `inherits` or `implements`. |
| `_swift_collect_type_refs()` | *top_level* | `Type Extraction` | Walk a Swift type expression and append (name, role) tuples. |
| `_swift_constructor_type()` | *top_level* | `Type Extraction` | If a Swift call expression is a constructor, return the type name. |
| `_swift_declaration_keyword()` | *top_level* | `Declaration Classification` | Return the leading kind token for a Swift class_declaration. |
| `_swift_extra_walk()` | *top_level* | `Node Handling` | Handles enum_entry for Swift. Returns True if handled. |
| `_swift_local_var_types()` | *top_level* | `Type Collection` | Collects ``var -> Type`` from local ``let``/``var`` bindings in a Swift. |
| `_swift_pre_scan()` | *top_level* | `Pre-Scan` | Pre-scan a Swift compilation unit and return (protocol_names, class_like_names). |
| `_swift_property_name()` | *top_level* | `Name Extraction` | Return the bound name of a Swift property. |
| `_swift_property_type_node()` | *top_level* | `Type Extraction` | Return the type_annotation child of a Swift property_declaration. |
| `_swift_receiver_name()` | *top_level* | `Name Extraction` | Return the depth-1 receiver name of a Swift member call. |
| `_swift_user_type_name()` | *top_level* | `Type Extraction` | Return the head type_identifier text from a Swift user_type node. |
| `_ts_decorator_name()` | *top_level* | `Decorator Name Extractor` | Returns the head symbol of a TypeScript decorator node. |
| `_ts_descendant_decorators()` | *top_level* | `Decorator Collector` | Collects decorator nodes under a given node. |
| `_ts_emit_decorator_edges()` | *top_level* | `Decorator Edge Emitter` | Emits reference edges for decorators in a class and its members. |
| `_ts_extra_walk()` | *top_level* | `Node Handling` | Emits a container node for a TS `namespace`/`module` declaration. |
| `_ts_method_name()` | *top_level* | `Method Name Extractor` | Extracts the name of a TypeScript method definition. |
| `_ts_receiver_type_table()` | *top_level* | `Type Collection` | Adds TS/JS receiver bindings to ``table`` (name -> TypeName), for member-call. |

#### Módulo: `graph/extractors/fortran.py` (310 LOC)
**Responsabilidade**: Módulo responsável pela extração de elementos de código Fortran.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_cpp_preprocess()` | *top_level* | `Parser / AST / Extração` | Executa cpp -w -P em um arquivo Fortran capital-F e retorna bytes pré-processados. |
| `extract_fortran()` | *top_level* | `Parser / AST / Extração` | Extrai programas, módulos, subrotinas, funções, declarações de uso e chamadas de arquivos Fortran. |

#### Módulo: `graph/extractors/go.py` (396 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos Go, incluindo funções, métodos, declarações de tipos e imports.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_go_collect_type_refs()` | *top_level* | `Parser / AST / Extração` | Percorre uma expressão de tipo Go e anexa tuplas (nome, papel). |
| `extract_go()` | *top_level* | `Parser / AST / Extração` | Extrai funções, métodos, declarações de tipos e imports de um arquivo .go. |

#### Módulo: `graph/extractors/json_config.py` (216 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos JSON de configuração ou manifesto, incluindo estrutura e dependências.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_is_config_json()` | *top_level* | `Validação / Segurança` | Verifica se um arquivo .json é um config/manifest reconhecido para AST-extrair. |
| `extract_json()` | *top_level* | `Parser / AST / Extração` | Extrai estrutura e arestas de dependência de um arquivo *config/manifest* .json. |

#### Módulo: `graph/extractors/julia.py` (275 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos Julia, incluindo módulos, estruturas, funções, imports e chamadas.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_julia()` | *top_level* | `Parser / AST / Extração` | Extrai módulos, estruturas, funções, imports e chamadas de um arquivo .jl. |

#### Módulo: `graph/extractors/markdown.py` (176 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos Markdown, incluindo nós estruturais e arestas.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_resolve_markdown_link()` | *top_level* | `Parser / AST / Extração` | Resolve um destino de link Markdown para o caminho absoluto de um documento irmão. |
| `extract_markdown()` | *top_level* | `Parser / AST / Extração` | Extrai nós estruturais e arestas de um arquivo Markdown. |

#### Módulo: `graph/extractors/models.py` (121 LOC)
**Responsabilidade**: Módulo contendo classes que representam diferentes tipos de fatos de símbolos usados na extração de AST.

*Módulo de constantes, tipos ou declarações puras sem funções executáveis.*

#### Módulo: `graph/extractors/objc.py` (430 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos Objective-C (.m, .mm, .h) para a construção de um grafo de conhecimento.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_objc_local_var_types()` | *top_level* | `Parser / AST / Extração` | Coleta tipos de variáveis locais de declarações Objective-C. |
| `extract_objc()` | *top_level* | `Parser / AST / Extração` | Extrai interfaces, implementações, protocolos, métodos e imports de arquivos Objective-C. |

#### Módulo: `graph/extractors/pascal.py` (688 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos Pascal/Delphi (.pas, .dpr) para a construção de um grafo de conhecimento.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_extract_pascal_regex()` | *top_level* | `Parser / AST / Extração` | Fallback regex para extração de Pascal/Delphi quando tree-sitter-pascal não está disponível. |
| `_pascal_find_body()` | *top_level* | `Parser / AST / Extração` | Encontra o corpo balanceado entre begin..end após o início. |
| `_pascal_split_bases()` | *top_level* | `Parser / AST / Extração` | Divide a lista de herança, tratando genéricos como TList<T, U>. |
| `_pascal_split_sections()` | *top_level* | `Parser / AST / Extração` | Divide o texto em seções de interface e implementação. |
| `_pascal_split_uses()` | *top_level* | `Parser / AST / Extração` | Divide a lista de imports, tratando a sintaxe 'Foo in ''bar.pas'''. |
| `_pascal_strip_comments()` | *top_level* | `Parser / AST / Extração` | Remove comentários Pascal preservando novas linhas. |
| `_resolve_pascal_callee_factory()` | *top_level* | `Parser / AST / Extração` | Constrói um resolvedor de chamadas scoped para um único arquivo Pascal/Delphi. |
| `extract_pascal()` | *top_level* | `Parser / AST / Extração` | Extrai unidades, classes, procedimentos, imports e chamadas de arquivos Pascal/Delphi. |

#### Módulo: `graph/extractors/pascal_forms.py` (196 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos de formulários Lazarus (.lfm) e Delphi (.dfm) para a construção de um grafo de conhecimento.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_delphi_form()` | *top_level* | `Parser / AST / Extração` | Extrai a hierarquia de componentes de arquivos de formulários Delphi. |
| `extract_lazarus_form()` | *top_level* | `Parser / AST / Extração` | Extrai a hierarquia de componentes de arquivos de formulários Lazarus. |

#### Módulo: `graph/extractors/powershell.py` (496 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos PowerShell (.ps1) e manifestos (.psd1) para a construção de um grafo de conhecimento.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_psd1_collect_string_literals()` | *top_level* | `Parser / AST / Extração` | Recursively coleta todos os valores de texto de literais de string sob *node*. |
| `_psd1_module_name()` | *top_level* | `Parser / AST / Extração` | Deriva um nome de módulo simples de um valor de string bruto. |
| `extract_powershell()` | *top_level* | `Parser / AST / Extração` | Extrai funções, classes, métodos e declarações using de arquivos PowerShell. |
| `extract_powershell_manifest()` | *top_level* | `Parser / AST / Extração` | Extrai arestas de dependência de módulo de arquivos de manifesto PowerShell. |

#### Módulo: `graph/extractors/razor.py` (119 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de componentes Razor e arquivos .cshtml para a construção de um grafo de conhecimento.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_razor()` | *top_level* | `Parser / AST / Extração` | Extrai diretivas, referências de componentes e métodos @code de arquivos Razor/.cshtml. |

#### Módulo: `graph/extractors/resolution.py` (2918 LOC)
**Responsabilidade**: Este módulo contém funções para resolver caminhos de importação, processar arquivos de configuração e extrair informações de diferentes linguagens de programação para a construção de um grafo de conhecimento.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_apply_symbol_resolution_facts()` | *top_level* | `Parser / AST / Extração` | Aplica fatos de resolução de símbolos fornecidos pelo idioma às arestas do grafo. |
| `_augment_symbol_resolution_edges()` | *top_level* | `Parser / AST / Extração` | Função interna sem documentação. |
| `_collect_js_symbol_resolution_facts()` | *top_level* | `Parser / AST / Extração` | Função interna sem documentação. |
| `_collect_python_symbol_resolution_facts()` | *top_level* | `Parser / AST / Extração` | Função interna sem documentação. |
| `_contained_in_package()` | *top_level* | `Validação / Segurança` | Garante que alvos de exportação não escapem do diretório do pacote. |
| `_decldef_class_stem()` | *top_level* | `Parser / AST / Extração` | Retorna (dir, base_stem) para um arquivo de cabeçalho/definição. |
| `_dentro_do_root()` | *top_level* | `Validação / Segurança` | Verifica se o alvo resolvido está dentro do root. |
| `_disambiguate_colliding_node_ids()` | *top_level* | `Parser / AST / Extração` | Reescreve IDs de nós conflitantes usando caminho de origem como disambiguador. |
| `_find_workspace_root()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_globs_linha_a_linha()` | *top_level* | `Parser / AST / Extração` | Lê globs de `packages:` sem parser de YAML. |
| `_is_type_like_definition()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_js_call_identifier()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_js_default_export_name()` | *top_level* | `Parser / AST / Extração` | Obtém o nome local de uma exportação padrão. |
| `_js_default_import_name()` | *top_level* | `Parser / AST / Extração` | Obtém o nome local de uma importação padrão. |
| `_js_export_clause()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_js_export_statement_is_star()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_js_exported_declaration_names()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_js_lexical_aliases()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_js_module_specifier()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_js_named_specifiers()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_js_namespace_export_name()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_js_source_path()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_js_top_level_function_bodies()` | *top_level* | `Parser / AST / Extração` | Função interna sem documentação. |
| `_load_tsconfig_aliases()` | *top_level* | `Parser / AST / Extração` | Carrega aliases de tsconfig a partir do diretório de início. |
| `_load_workspace_packages()` | *top_level* | `Parser / AST / Extração` | Carrega pacotes de workspace. |
| `_match_tsconfig_alias()` | *top_level* | `Parser / AST / Extração` | Corresponde padrões de alias de tsconfig. |
| `_merge_decl_def_classes()` | *top_level* | `Parser / AST / Extração` | Mescla uma classe declarada em um cabeçalho com sua definição em um arquivo de definição. |
| `_nao_diretorio()` | *top_level* | `Validação / Segurança` | Retorna None quando a resolução cai em um diretório existente. |
| `_node_disambiguation_source_key()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_package_entry_candidates()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_parse_js_tree()` | *top_level* | `Parser / AST / Extração` | Função interna sem documentação. |
| `_parse_python_tree()` | *top_level* | `Parser / AST / Extração` | Função interna sem documentação. |
| `_pascal_project_root()` | *top_level* | `Parser / AST / Extração` | Retorna o diretório mais alto que parece ser a raiz de um projeto Pascal. |
| `_pascal_resolve_class()` | *top_level* | `Parser / AST / Extração` | Resolve um nome de classe/interface Pascal para o node ID do nó de classe definido no arquivo. |
| `_pascal_resolve_unit()` | *top_level* | `Parser / AST / Extração` | Resolve um nome de unidade Pascal para o node ID do arquivo de origem. |
| `_php_fqn_from_raw()` | *top_level* | `Parser / AST / Extração` | Resolve uma referência de classe PHP bruta para um FQN. |
| `_pnpm_workspace_globs()` | *top_level* | `Parser / AST / Extração` | Obtém globs de pnpm-workspace.yaml. |
| `_probe_python_module_candidate()` | *top_level* | `Parser / AST / Extração` | Resolve um candidato de caminho de módulo para um arquivo .py. |
| `_python_call_identifier()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_python_import_from_module()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_python_imported_names()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_python_top_level_function_bodies()` | *top_level* | `Parser / AST / Extração` | Função interna sem documentação. |
| `_read_tsconfig_aliases()` | *top_level* | `Parser / AST / Extração` | Lê aliases de tsconfig recursivamente. |
| `_resolve_c_include_path()` | *top_level* | `Parser / AST / Extração` | Resolve caminhos de #include em C para arquivos reais no disco. |
| `_resolve_cross_file_imports()` | *top_level* | `Parser / AST / Extração` | Resolução de importações entre arquivos em duas passagens. |
| `_resolve_cross_file_java_imports()` | *top_level* | `Parser / AST / Extração` | Resolução de importações Java em duas passagens. |
| `_resolve_export_target()` | *top_level* | `Parser / AST / Extração` | Resolve alvos de exportação. |
| `_resolve_java_type_references()` | *top_level* | `Parser / AST / Extração` | Reaponta arestas de implements/inherits em Java para os nós reais. |
| `_resolve_js_import_path()` | *top_level* | `Parser / AST / Extração` | Resolve caminhos de importação de JS/TS/Svelte para arquivos locais. |
| `_resolve_js_import_target()` | *top_level* | `Parser / AST / Extração` | Resolve caminhos de importação JS/TS para (target_nid, resolved_path). |
| `_resolve_js_module_path()` | *top_level* | `Parser / AST / Extração` | Resolve caminhos de módulo JS/TS para arquivos de origem locais. |
| `_resolve_lua_import_target()` | *top_level* | `Parser / AST / Extração` | Resolve nomes de módulo require() em Lua para node id. |
| `_resolve_php_type_references()` | *top_level* | `Parser / AST / Extração` | Desambigua alvos de inherits/implements/mixes_in/imports/references em PHP. |
| `_resolve_python_module_path()` | *top_level* | `Parser / AST / Extração` | Função interna sem documentação. |
| `_resolve_tsconfig_alias()` | *top_level* | `Parser / AST / Extração` | Resolve aliases de tsconfig. |
| `_resolve_workspace_import()` | *top_level* | `Parser / AST / Extração` | Resolve imports de workspace. |
| `_root_corrente()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_source_key()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `_strip_jsonc()` | *top_level* | `Parser / AST / Extração` | Remove comentários e vírgulas extras de arquivos JSONC. |
| `_ts_collect_type_refs()` | *top_level* | `Parser / AST / Extração` | Percorre uma árvore de anotação de tipo TS; anexa tuplas (nome, papel). |
| `_ts_heritage_clause_entries()` | *top_level* | `Parser / AST / Extração` | Obtém nomes de tipos base/interface de uma cláusula extends/implements. |
| `_ts_walk_class_members()` | *top_level* | `Parser / AST / Extração` | Emite fatos de uso de relação de tipo e referência de tipo para um nó de declaração de classe. |
| `_vue_mask_non_script()` | *top_level* | `Parser / AST / Extração` | Oculta tudo fora de blocos <script> em arquivos Vue. |
| `_walk_js_tree()` | *top_level* | `Parser / AST / Extração` | Função interna sem documentação. |
| `_walk_python_tree()` | *top_level* | `Parser / AST / Extração` | Função interna sem documentação. |
| `_workspace_globs()` | *top_level* | `Utilitário / Helper` | Função interna sem documentação. |
| `escopo_de_root()` | *top_level* | `Orquestração / Lifecycle` | Marca a raiz do scan enquanto o bloco roda. |

#### Módulo: `graph/extractors/rust.py` (410 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos Rust usando tree-sitter.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_rust_collect_type_refs()` | *top_level* | `Parser / AST / Extração` | Percorre uma expressão de tipo Rust; anexa tuplas (nome, papel). |
| `extract_rust()` | *top_level* | `Parser / AST / Extração` | Extrai funções, structs, enums, traits, métodos impl e declarações use de um arquivo .rs. |

#### Módulo: `graph/extractors/sln.py` (92 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos .sln.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_sln()` | *top_level* | `Parser / AST / Extração` | Extrai projetos e dependências entre projetos de um arquivo .sln. |

#### Módulo: `graph/extractors/sql.py` (295 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos SQL usando tree-sitter.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_sql()` | *top_level* | `Parser / AST / Extração` | Extrai tabelas, visualizações, funções e relações de arquivos .sql via tree-sitter. |

#### Módulo: `graph/extractors/terraform.py` (181 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos Terraform/HCL usando tree-sitter.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_terraform()` | *top_level* | `Parser / AST / Extração` | Extrai blocos Terraform/HCL e as referências entre eles via tree-sitter. |

#### Módulo: `graph/extractors/verilog.py` (329 LOC)
**Responsabilidade**: Módulo responsável por extrair informações de arquivos Verilog.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_augment_systemverilog_semantics()` | *top_level* | `Parser / AST / Extração` | Função não documentada. |
| `_sv_child()` | *top_level* | `Parser / AST / Extração` | Função não documentada. |
| `_sv_collect_type_refs()` | *top_level* | `Parser / AST / Extração` | Função não documentada. |
| `_sv_first_identifier()` | *top_level* | `Parser / AST / Extração` | Primeiro `simple_identifier` sob o nó em pré-ordem, ou None. |
| `_sv_split_type_list()` | *top_level* | `Parser / AST / Extração` | Função não documentada. |
| `_sv_strip_comments()` | *top_level* | `Parser / AST / Extração` | Função não documentada. |
| `extract_verilog()` | *top_level* | `Parser / AST / Extração` | Extrai módulos, funções, tarefas, importações de pacotes, instâncias e |

#### Módulo: `graph/extractors/zig.py` (175 LOC)
**Responsabilidade**: Módulo responsável pela extração de elementos de arquivos Zig usando Tree-sitter.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `extract_zig()` | *top_level* | `Parser / AST / Extração` | Extrai funções, estruturas, enums, uniões e imports de um arquivo .zig. |

#### Módulo: `graph/ids.py` (50 LOC)
**Responsabilidade**: Módulo que fornece normalização de IDs de nós.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `make_id()` | *top_level* | `Parser / AST / Extração` | Constrói um ID de nó canônico a partir de uma ou mais partes de nome. |
| `normalize_id()` | *top_level* | `Parser / AST / Extração` | Normaliza uma única string de ID para seu formato canônico. |

#### Módulo: `graph/manifest_ingest.py` (263 LOC)
**Responsabilidade**: Módulo responsável pela ingestão determinística de arquivos de manifesto de pacote.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_coerce_deps()` | *top_level* | `Parser / AST / Extração` | Um bloco de dependência pode ser uma lista de nomes ou um mapa nome->especificação. |
| `_parse_apm()` | *top_level* | `Parser / AST / Extração` | Função interna para parsear arquivos APM. |
| `_parse_apm_fallback()` | *top_level* | `Parser / AST / Extração` | Parseador minimalista para apm.yml quando PyYAML não está disponível. |
| `_parse_gomod()` | *top_level* | `Parser / AST / Extração` | Função interna para parsear arquivos go.mod. |
| `_parse_pom()` | *top_level* | `Parser / AST / Extração` | Função interna para parsear arquivos pom.xml. |
| `_parse_pyproject()` | *top_level* | `Parser / AST / Extração` | Função interna para parsear arquivos pyproject.toml. |
| `_pep508_name()` | *top_level* | `Parser / AST / Extração` | Extrai o nome do pacote de uma especificação PEP508. |
| `_pkg_id()` | *top_level* | `Parser / AST / Extração` | ID de nó de pacote canônico, chaveado pelo NOME do pacote. |
| `_xml_is_safe()` | *top_level* | `Validação / Segurança` | Rejeita XML que declara um DTD ou entidade (guarda contra billion laughs). |
| `extract_package_manifest()` | *top_level* | `Parser / AST / Extração` | Parseia um arquivo de manifesto de pacote em um nó de pacote canônico + arestas ``depends_on``. |
| `is_package_manifest_path()` | *top_level* | `Validação / Segurança` | Retorna True se ``path`` for um nome de arquivo de manifesto de pacote reconhecido. |

#### Módulo: `graph/pascal_resolution.py` (129 LOC)
**Responsabilidade**: Módulo responsável pela resolução cruzada de chamadas a métodos herdados em Pascal/Delphi.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_pascal_raw_calls()` | *top_level* | `Parser / AST / Extração` | Extrai chamadas brutas em Pascal/Delphi. |
| `resolve_pascal_inherited_calls()` | *top_level* | `Handler MCP / Endpoint` | Resolve chamadas a métodos herdados em Pascal/Delphi entre arquivos. |

#### Módulo: `graph/paths.py` (304 LOC)
**Responsabilidade**: Módulo que fornece funções utilitárias para manipulação de caminhos e escrita atômica.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_atomic_replace()` | *top_level* | `Utilitário / Helper` | Substitui atomicamente um caminho com conteúdo escrito por uma função. |
| `_is_test_path()` | *top_level* | `Validação / Segurança` | Classifica um caminho de origem como um caminho de teste. |
| `_path_proximity_winner()` | *top_level* | `Cálculo / Algoritmo` | Escolhe o candidato cujo arquivo de origem está mais próximo do local da chamada. |
| `default_graph_json()` | *top_level* | `Utilitário / Helper` | Retorna o caminho padrão para ``graph.json`` no diretório de saída configurado. |
| `disambiguate_ambiguous_candidates()` | *top_level* | `Handler MCP / Endpoint` | Resolve uma chamada de nome simples ambígua para um candidato ou ``None``. |
| `out_path()` | *top_level* | `Utilitário / Helper` | Retorna um caminho dentro do diretório de saída configurado. |
| `write_json_atomic()` | *top_level* | `Utilitário / Helper` | Escreve atomicamente um objeto como JSON para um caminho. |
| `write_text_atomic()` | *top_level* | `Utilitário / Helper` | Escreve atomicamente texto UTF-8 para um caminho. |

#### Módulo: `graph/report.py` (300 LOC)
**Responsabilidade**: Módulo responsável pela geração de relatórios a partir de dados de aprendizado.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_learning_section()` | *top_level* | `Handler MCP / Endpoint` | Anexa a seção ``## Work-memory lessons``, ou nada quando vazia. |
| `_safe_community_name()` | *top_level* | `Utilitário / Helper` | Garante que nomes de comunidade e relatórios de wiki sempre concordem. |
| `generate()` | *top_level* | `Handler MCP / Endpoint` | Gera o relatório. |
| `load_learning_for_report()` | *top_level* | `Leitura / Consulta` | Monta as entradas de memória de trabalho do relatório a partir de artefatos irmãos. |

#### Módulo: `graph/resolver_registry.py` (85 LOC)
**Responsabilidade**: Módulo que registra e executa resolvers cruzados específicos de linguagem.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `register()` | *top_level* | `Orquestração / Lifecycle` | Registra um resolver no registro global e o retorna. |
| `registered_resolvers()` | *top_level* | `Leitura / Consulta` | Retorna uma cópia dos resolvers registrados, na ordem de registro. |
| `run_language_resolvers()` | *top_level* | `Orquestração / Lifecycle` | Executa todos os resolvers cujo suporte aparece em ``paths``. |

#### Módulo: `graph/ruby_resolution.py` (169 LOC)
**Responsabilidade**: Módulo responsável pela resolução cruzada de chamadas de membros em Ruby.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_key()` | *top_level* | `Parser / AST / Extração` | Normaliza um rótulo de classe/método para uma chave de comparação (remove pontuação). |
| `_ruby_raw_calls()` | *top_level* | `Parser / AST / Extração` | Extrai chamadas brutas em Ruby. |
| `resolve_ruby_member_calls()` | *top_level* | `Handler MCP / Endpoint` | Resolve chamadas de membros em Ruby ``Class.new`` e ``var.method`` por tipo de receptor. |

#### Módulo: `graph/wiki.py` (337 LOC)
**Responsabilidade**: Módulo responsável por funções relacionadas à geração de wikis a partir do gráfico.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_community_article()` | *top_level* | `Leitura / Consulta` | Função não documentada. |
| `_cross_community_links()` | *top_level* | `Leitura / Consulta` | Retorna pares (rótulo da comunidade, contagem de arestas) para conexões entre comunidades, ordenados em ordem decrescente. |
| `_god_node_article()` | *top_level* | `Leitura / Consulta` | Função não documentada. |
| `_index_md()` | *top_level* | `Leitura / Consulta` | Função não documentada. |
| `_md_link()` | *top_level* | `Utilitário / Helper` | Renderiza um link para outro artigo wiki como um link markdown portátil relativo. |
| `_safe_filename()` | *top_level* | `Utilitário / Helper` | Torna um rótulo seguro para uso como nome de arquivo em diferentes plataformas. |
| `to_wiki()` | *top_level* | `Mutação / Escrita` | Gera um wiki estilo Wikipedia a partir do gráfico. |

#### Módulo: `graphbridge.py` (738 LOC)
**Responsabilidade**: Orquestra o pipeline de construção do grafo de conhecimento, incluindo carregamento, salvamento e manipulação de registros.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_clear_previous_filing()` | *top_level* | `Mutação / Escrita` | Remove as notas do vault previamente arquivadas antes de re-arquivar. |
| `_frontmatter()` | *top_level* | `Parser / AST / Extração` | Extrai o frontmatter de um arquivo. |
| `_load_registry()` | *top_level* | `Leitura / Consulta` | Carrega o registro de grafos previamente construídos. |
| `_resolve_folder()` | *top_level* | `Leitura / Consulta` | Resolve o caminho da pasta do vault de forma insensível a maiúsculas e minúsculas. |
| `_save_registry()` | *top_level* | `Mutação / Escrita` | Salva o registro de grafos atualizado. |
| `_slugify()` | *top_level* | `Utilitário / Helper` | Converte uma string em um slug (formato de URL amigável). |
| `_write_artifacts_to_vault()` | *top_level* | `Mutação / Escrita` | Arquiva o relatório do grafo e os artigos wiki no vault. |
| `_write_vault_note()` | *top_level* | `Mutação / Escrita` | Escreve uma nota no vault diretamente, incluindo indexação e links wikilinks. |
| `_write_wiki_article()` | *top_level* | `Mutação / Escrita` | Escreve um artigo wiki em uma pasta específica, mantendo o nome original. |
| `build_graph()` | *top_level* | `Orquestração / Lifecycle` | Constrói um grafo de conhecimento para um caminho de origem usando o pipeline fornecido. |
| `export_graph()` | *top_level* | `Exportação` | Re-exporta um grafo existente para outro formato. |
| `extract_source_maps()` | *top_level* | `Parser / AST / Extração` | Reconstrói as origens originais a partir de todos os .js.map utilizáveis. |
| `find_source_maps()` | *top_level* | `Leitura / Consulta` | Encontra arquivos de mapa de origem (.map) associados a pacotes JS. |
| `get_affected()` | *top_level* | `Leitura / Consulta` | Consulta de raio de impacto: o que mais está afetado se `query` (um caminho de arquivo ou símbolo) for alterado. |
| `get_report()` | *top_level* | `Leitura / Consulta` | Retorna o texto completo do relatório do grafo para um grafo previamente construído pelo nome. |
| `list_graphs()` | *top_level* | `Leitura / Consulta` | Retorna o registro de grafos previamente construídos: nome, caminho de origem, contagens e timestamps. |
| `preview_graph()` | *top_level* | `Leitura / Consulta` | Relata o que a construção de um grafo cobriria, sem construí-lo. |

### Domínio: `Vault & Storage`
> **Módulos**: 16 | **Funções**: 183 | **LOC**: 6,947

#### Módulo: `downloader.py` (365 LOC)
**Responsabilidade**: Responsável por baixar modelos GGUF e o binário llama.cpp para o Vault.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_common_dir_prefix()` | *top_level* | `Utilitário / Helper` | Retorna o prefixo comum de diretório compartilhado entre entradas. |
| `_download_file()` | *top_level* | `Mutação / Escrita` | Baixa um arquivo. |
| `_get_release_asset()` | *top_level* | `Leitura / Consulta` | Obtém um ativo de lançamento. |
| `_is_plain_cpu_asset()` | *top_level* | `Validação / Segurança` | Verifica se um ativo é para CPU. |
| `download_llama_binary()` | *top_level* | `Mutação / Escrita` | Baixa o binário mais recente do llama-server do GitHub releases. |
| `download_model()` | *top_level* | `Mutação / Escrita` | Baixa um modelo GGUF. |
| `find_llama_binary()` | *top_level* | `Leitura / Consulta` | Retorna um binário llama-server existente ou None. |

#### Módulo: `extractor.py` (441 LOC)
**Responsabilidade**: Converte formatos de arquivo para texto simples para ingestão no Vault.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_csv_to_md()` | *top_level* | `Parser / AST / Extração` | Converte um arquivo CSV para Markdown. |
| `_docx()` | *top_level* | `Parser / AST / Extração` | Extrai texto de um arquivo DOCX. |
| `_first_byte_readable()` | *top_level* | `Validação / Segurança` | Verifica se um byte pode ser lido do arquivo sem bloqueio. |
| `_html()` | *top_level* | `Parser / AST / Extração` | Extrai texto de uma página HTML. |
| `_imagem()` | *top_level* | `Parser / AST / Extração` | Extrai texto de uma imagem. |
| `_json()` | *top_level* | `Parser / AST / Extração` | Extrai texto de um arquivo JSON. |
| `_pdf()` | *top_level* | `Parser / AST / Extração` | Extrai texto de um arquivo PDF. |
| `_pptx()` | *top_level* | `Parser / AST / Extração` | Extrai texto de um arquivo PPTX. |
| `_text()` | *top_level* | `Parser / AST / Extração` | Extrai texto de um arquivo de texto. |
| `_xlsx()` | *top_level* | `Parser / AST / Extração` | Extrai texto de um arquivo XLSX. |
| `extract()` | *top_level* | `Leitura / Consulta` | Retorna texto simples extraído de um caminho. |
| `extract_pages()` | *top_level* | `Leitura / Consulta` | Retorna texto por página para PDFs. |
| `format_label()` | *top_level* | `Utilitário / Helper` | Retorna um nome de formato legível para um caminho de arquivo. |
| `is_dataless()` | *top_level* | `Validação / Segurança` | Verifica se um arquivo existe mas seu conteúdo foi evictado para armazenamento em nuvem. |
| `is_no_text_stub()` | *top_level* | `Validação / Segurança` | Verifica se o texto extraído é um stub vazio. |
| `materialize_if_dataless()` | *top_level* | `Mutação / Escrita` | Tenta acionar o download de arquivo em nuvem sob demanda se for dataless. |
| `no_text_stub()` | *top_level* | `Validação / Segurança` | Verifica se o registro de um arquivo não extraiu uma linha de texto. |
| `sem_substancia()` | *top_level* | `Validação / Segurança` | Verifica se o texto extraído é muito fino para justificar uma nota sintetizada. |
| `tessdata_padrao()` | *top_level* | `Utilitário / Helper` | Retorna o diretório padrão para tessdata. |

#### Módulo: `imagens/leitura.py` (176 LOC)
**Responsabilidade**: Módulo responsável por processar imagens, extrair metadados e realizar OCR para tornar o conteúdo buscável.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_exif()` | *top_level* | `Leitura / Consulta` | Extrai os metadados EXIF da imagem. |
| `data_da_captura()` | *top_level* | `Leitura / Consulta` | Extrai a data de captura da imagem. |
| `idiomas_disponiveis()` | *top_level* | `Leitura / Consulta` | Lista os idiomas disponíveis para OCR. |
| `ler_imagem()` | *top_level* | `Leitura / Consulta` | Processa a imagem para extrair informações relevantes. |
| `markdown_tem_texto()` | *top_level* | `Leitura / Consulta` | Verifica se a nota de imagem contém texto lido ou apenas metadados. |
| `ocr()` | *top_level* | `Leitura / Consulta` | Realiza OCR na imagem, retornando o texto extraído ou um motivo caso falhe. |
| `para_markdown()` | *top_level* | `Mutação / Escrita` | Converte o conteúdo extraído para formato Markdown. |

#### Módulo: `ingest.py` (728 LOC)
**Responsabilidade**: Responsável pela ingestão de arquivos externos no índice de pesquisa do Vault sem alterar os arquivos no disco.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__init__()` | `IngestManager` | `Orquestração / Lifecycle` | Inicializa o gerenciador de ingestão. |
| `_arquivos_no_indice()` | `IngestManager` | `Leitura / Consulta` | Retorna os arquivos que o índice tem de fato ou None se não for possível saber. |
| `_configured_source_for()` | `IngestManager` | `Leitura / Consulta` | Encontra a fonte lógica e o caminho físico que autorizam a fonte. |
| `forget()` | `IngestManager` | `Mutação / Escrita` | Remove tudo que foi anteriormente ingerido de source_path. |
| `ingest()` | `IngestManager` | `Mutação / Escrita` | Indexa todos os arquivos suportados sob source_path. |
| `ingest_configured()` | `IngestManager` | `Mutação / Escrita` | Ingestiona uma fonte configurada nomeada ou todas as fontes habilitadas quando o nome está vazio. |
| `status()` | `IngestManager` | `Leitura / Consulta` | Retorna o registro de ingestão: quais caminhos foram indexados, contagens de arquivos e existência. |
| `_atomic_write_registry()` | *top_level* | `Mutação / Escrita` | Escreve atomicamente o registro de ingestão. |
| `_configured_sources()` | *top_level* | `Leitura / Consulta` | Retorna entradas de fonte com pelo menos um caminho físico utilizável. |
| `_fontes_do_indice_sqlite()` | *top_level* | `Leitura / Consulta` | O mesmo que `fontes_do_indice`, para o índice SQLite. |
| `_has_source_policy()` | *top_level* | `Validação / Segurança` | Uma lista configurada não vazia é uma lista de permissão, mesmo se uma entrada estiver malformada. |
| `_load_registry()` | *top_level* | `Leitura / Consulta` | O registro de ingestão ou um dicionário vazio quando o arquivo não serve. |
| `_merge_patterns()` | *top_level* | `Parser / AST / Extração` | Combina padrões configurados e por execução sem alterar sua ordem. |
| `_paged_get()` | *top_level* | `Leitura / Consulta` | Obtém linhas de ChromaDB em lotes para evitar 'too many SQL variables'. |
| `_remove_source_entry()` | *top_level* | `Mutação / Escrita` | Remove uma entrada de fonte. |
| `_save_registry()` | *top_level* | `Mutação / Escrita` | Salva o registro de ingestão. |
| `_source_paths()` | *top_level* | `Leitura / Consulta` | Expande uma fonte lógica em seus caminhos físicos. |
| `_update_source_entry()` | *top_level* | `Mutação / Escrita` | Atualiza uma entrada de fonte. |
| `fontes_do_indice()` | *top_level* | `Leitura / Consulta` | As fontes ingeridas que um índice guarda. |
| `is_excluded()` | *top_level* | `Validação / Segurança` | Determina se um padrão glob de `exclude` mantém este arquivo fora. |
| `reconstruir_registro_do_indice()` | *top_level* | `Leitura / Consulta` | Devolve as fontes do índice em `chroma_dir` somadas ao registro atual. |

#### Módulo: `linker.py` (341 LOC)
**Responsabilidade**: Módulo responsável pela geração e manipulação de wikilinks e frontmatter de notas.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_alias_block()` | *top_level* | `Parser / AST / Extração` | Renderiza um bloco YAML `aliases:` com valores devidamente citados. |
| `_to_stem()` | *top_level* | `Parser / AST / Extração` | Extrai a parte do nome do arquivo sem manipular pontos internos. |
| `add_related_links()` | *top_level* | `Mutação / Escrita` | Anexa novos links relacionados à seção `## Related`, criando-a se ausente. |
| `clean_display()` | *top_level* | `Parser / AST / Extração` | Gera um rótulo legível para uma nota, preferindo o título do frontmatter, se disponível. |
| `ensure_aliases()` | *top_level* | `Mutação / Escrita` | Mescla entradas no frontmatter `aliases:` de uma nota, criando frontmatter se necessário. |
| `existing_targets()` | *top_level* | `Leitura / Consulta` | Retorna o conjunto de títulos de notas já vinculadas em uma nota. |
| `format_link()` | *top_level* | `Parser / AST / Extração` | Constrói um link wikilink formatado `[[stem-Display]]` ou `[[stem]]`. |
| `inject_backlinks()` | *top_level* | `Mutação / Escrita` | Injeta um link de volta para a nota de origem se não estiver presente. |
| `relink_folder()` | *top_level* | `Mutação / Escrita` | Adiciona wikilinks relacionados para notas em uma subpasta do vault. |
| `strip_frontmatter()` | *top_level* | `Parser / AST / Extração` | Remove o frontmatter YAML de um corpo de nota. |
| `wikilinks()` | *top_level* | `Leitura / Consulta` | Retorna um bloco `- [[stem-Display]]` para notas existentes. |

#### Módulo: `merger.py` (106 LOC)
**Responsabilidade**: Módulo responsável por tentar mesclar notas próximas em duplicidade.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_never_merge()` | *top_level* | `Utilitário / Helper` | Retorna as pastas protegidas de merge, minusculas, config mais os padrões. |
| `try_merge()` | *top_level* | `Mutação / Escrita` | Tenta mesclar note_content em uma existente próxima duplicidade. |

#### Módulo: `notes.py` (703 LOC)
**Responsabilidade**: Módulo para lidar com nomes de notas, caminhos e frontmatter.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_countable_wikilinks()` | *top_level* | `Parser / AST / Extração` | Retorna note-like wikilink targets from a note, excluding code spans and. |
| `_frontmatter_parses()` | *top_level* | `Validação / Segurança` | Does this note's frontmatter block survive a real YAML parser? |
| `_merge_alias()` | *top_level* | `Mutação / Escrita` | Add `alias` to an existing `aliases:` value, block-list or inline. |
| `atualizar_estado()` | *top_level* | `Orquestração / Lifecycle` | Ler, modificar e gravar sob UMA trava, que é o ponto desta função. |
| `caminho_do_estado()` | *top_level* | `Utilitário / Helper` | Função de caminho do estado. |
| `carregar_estado()` | *top_level* | `Leitura / Consulta` | Devolve {} para arquivo ausente ou ilegível, avisando no segundo caso. |
| `client_from_path()` | *top_level* | `Parser / AST / Extração` | Derive a client from an external file's path, or "" when unsure. |
| `client_slug()` | *top_level* | `Utilitário / Helper` | Normalise a client name to the single form the index is keyed by. |
| `compose_note()` | *top_level* | `Mutação / Escrita` | Build note text carrying exactly one YAML frontmatter block. |
| `frontmatter_aliases()` | *top_level* | `Parser / AST / Extração` | Return the set of Obsidian `aliases:` declared in a note's frontmatter. |
| `gravar_estado()` | *top_level* | `Mutação / Escrita` | Escrita atômica, com temporário ÚNICO por processo e thread. |
| `ingested_link_stems()` | *top_level* | `Parser / AST / Extração` | Nomes pelos quais um arquivo ingerido de fora do vault pode ser linkado. |
| `link_names_for_stem()` | *top_level* | `Parser / AST / Extração` | Every name a note with this filename stem can be linked by, lowercased. |
| `resolve_in_vault()` | *top_level* | `Utilitário / Helper` | Resolve *rel_path* under *vault_root*, or None if it escapes. |
| `resolve_vault_folder()` | *top_level* | `Utilitário / Helper` | Resolve a folder name against cfg.vault_folders case-insensitively. |
| `safe_filename()` | *top_level* | `Utilitário / Helper` | Sanitize a title into a filesystem-safe filename stem. |
| `unique_note_path()` | *top_level* | `Mutação / Escrita` | Disambiguate a note destination that already exists on disk. |
| `yaml_quote_scalar()` | *top_level* | `Parser / AST / Extração` | Double-quote a string for safe use as a YAML frontmatter scalar value. |
| `yaml_unquote_scalar()` | *top_level* | `Parser / AST / Extração` | Reverse yaml_quote_scalar() for frontmatter values read back with naive line parsing. |

#### Módulo: `notewriter.py` (285 LOC)
**Responsabilidade**: Módulo responsável por escrever, salvar e gerenciar notas no Vault, incluindo a criação de links e renomeação de notas.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_retarget()` | *top_level* | `Mutação / Escrita` | Redireciona todos os links wiki para um novo destino, mantendo seções e partes de exibição. |
| `create_note()` | *top_level* | `Mutação / Escrita` | Cria uma nova nota datada no diretório especificado e a indexa. |
| `post_write_links()` | *top_level* | `Mutação / Escrita` | Injeta links wiki após a escrita de uma nota no Vault. |
| `rename_note()` | *top_level* | `Mutação / Escrita` | Renomeia uma nota e redireciona todos os links wiki que a referenciavam. |
| `save_note()` | *top_level* | `Mutação / Escrita` | Substitui o texto completo de uma nota existente e a reindexa. |

#### Módulo: `organizer.py` (666 LOC)
**Responsabilidade**: Módulo responsável pela manutenção do Vault, incluindo a re-síntese de notas de baixa qualidade e a organização de seções.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_archive_sidecar()` | *top_level* | `Mutação / Escrita` | Move o arquivo .meta.yaml (se existir) para o diretório processed/. |
| `_archive_sidecars()` | *top_level* | `Mutação / Escrita` | Arquiva os arquivos .meta.yaml. |
| `_inject_quality_frontmatter()` | *top_level* | `Mutação / Escrita` | Injeta ou atualiza a pontuação de qualidade, problemas e necessidade de revisão no frontmatter YAML de uma nota. |
| `_is_placeholder()` | *top_level* | `Validação / Segurança` | Verifica se uma nota é um placeholder. |
| `_merge_forbidden()` | *top_level* | `Validação / Segurança` | Verifica se uma nota deve ser explicitamente excluída da mesclagem em uma nota existente. |
| `_process_sections()` | *top_level* | `Mutação / Escrita` | Sintetiza, mescla ou arquiva cada seção de uma divisão recursiva. |
| `_resumo_de_manutencao()` | *top_level* | `Cálculo / Algoritmo` | Gera o corpo do resumo semanal, separado para testabilidade. |
| `_resumo_deterministico()` | *top_level* | `Cálculo / Algoritmo` | Gera um resumo determinístico a partir dos números presentes no texto. |
| `_synthesis_quality()` | *top_level* | `Cálculo / Algoritmo` | Avalia a qualidade da síntese de uma nota e retorna uma pontuação e uma lista de problemas. |
| `_titulo_de_secao()` | *top_level* | `Parser / AST / Extração` | Gera um título de 3 a 5 palavras para uma seção cujo título é apenas um marcador. |
| `_upgrade_section_titles()` | *top_level* | `Mutação / Escrita` | Substitui títulos de seção de placeholder por títulos descritivos gerados por LLM. |
| `_write_summary()` | *top_level* | `Mutação / Escrita` | Anexa uma seção de manutenção datada ao nota de resumo semanal. |
| `heal()` | *top_level* | `Mutação / Escrita` | Re-sintetiza notas de baixa qualidade, limitado por cfg.heal_per_run por chamada. |
| `run()` | *top_level* | `Orquestração / Lifecycle` | Executa o pipeline de manutenção do Vault. |

#### Módulo: `recuperacao.py` (326 LOC)
**Responsabilidade**: Módulo responsável pela recuperação e manutenção do índice do Vault, incluindo a reconstrução do índice em caso de falha.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_dir_de_estado()` | *top_level* | `Leitura / Consulta` | Obtém o diretório de estado. |
| `_gravar_json()` | *top_level* | `Mutação / Escrita` | Grava um arquivo JSON. |
| `_ler_json()` | *top_level* | `Leitura / Consulta` | Lê um arquivo JSON. |
| `_pid_vivo()` | *top_level* | `Validação / Segurança` | Verifica se um PID está vivo. |
| `antes_de_abrir()` | *top_level* | `Validação / Segurança` | Chamado antes de abrir o índice, retorna True se o índice está em quarentena. |
| `caminho_do_marcador()` | *top_level* | `Leitura / Consulta` | Obtém o caminho do marcador. |
| `caminho_do_pedido()` | *top_level* | `Leitura / Consulta` | Obtém o caminho do pedido. |
| `depois_de_abrir()` | *top_level* | `Mutação / Escrita` | Chamado após o índice ser aberto e responder, marcando que a abertura não é mais suspeita. |
| `falha_da_sonda()` | *top_level* | `Validação / Segurança` | Verifica se a sonda do doctor conseguiu abrir e consultar o índice. |
| `pos_em_quarentena()` | *top_level* | `Mutação / Escrita` | Tira o índice do caminho, zera os carimbos e solicita a reconstrução. |
| `reconstrucao_pendente()` | *top_level* | `Validação / Segurança` | Verifica se uma reconstrução está pendente. |
| `reconstruir()` | *top_level* | `Mutação / Escrita` | Refaz o índice a partir das fontes: as notas do Vault e cada ingestão. |

#### Módulo: `repair.py` (216 LOC)
**Responsabilidade**: Módulo responsável por reparar notas que foram sintetizadas incorretamente.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_ja_tratada()` | *top_level* | `Validação / Segurança` | Verifica se uma nota já foi tratada ou se não pode ser lida. |
| `_normalizar()` | *top_level* | `Parser / AST / Extração` | Normaliza um nome reduzindo variações de separador. |
| `_notas_da_origem()` | *top_level* | `Leitura / Consulta` | Retorna as notas geradas a partir de um arquivo. |
| `_origens()` | *top_level* | `Leitura / Consulta` | Retorna os arquivos consumidos pelo pipeline. |
| `_troca_o_corpo()` | *top_level* | `Mutação / Escrita` | Substitui o corpo de uma nota pelo toco, preservando o frontmatter. |
| `aplicar()` | *top_level* | `Mutação / Escrita` | Aplica reparos nas notas identificadas. |
| `encontrar()` | *top_level* | `Leitura / Consulta` | Identifica origens sem texto suficiente e as notas geradas delas. |

#### Módulo: `session.py` (78 LOC)
**Responsabilidade**: Módulo responsável por exportar uma sessão curada para a pasta sessions/ do vault.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `export()` | *top_level* | `Mutação / Escrita` | Escreve uma nota de sessão formatada para a pasta sessions/ do vault e a indexa imediatamente. |

#### Módulo: `sidecar.py` (104 LOC)
**Responsabilidade**: Módulo responsável por arquivos YAML de metadados sidecar para ingestão de inbox.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `format_block()` | *top_level* | `Parser / AST / Extração` | Renderiza o sidecar como uma lista de itens para injeção em um prompt de síntese. |
| `is_sidecar()` | *top_level* | `Validação / Segurança` | Verifica se o caminho é um arquivo de metadados sidecar (não um arquivo de conteúdo principal). |
| `load()` | *top_level* | `Leitura / Consulta` | Carrega e analisa o sidecar para main_path. Retorna {} se o YAML estiver ausente ou inválido. |
| `resolve_folder_hint()` | *top_level* | `Parser / AST / Extração` | Resolve o `folder_hint` do sidecar, com a caixa do vault, ou retorna None se inválido. |
| `sidecar_for()` | *top_level* | `Leitura / Consulta` | Retorna o caminho do sidecar para main_path se existir no disco, caso contrário, retorna None. |

#### Módulo: `splitter.py` (201 LOC)
**Responsabilidade**: Módulo responsável por dividir notas grandes em partes menores com base em cabeçalhos, páginas PDF e parágrafos.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_paragraph_chunks()` | *top_level* | `Parser / AST / Extração` | Divide o texto em partes de parágrafos próximos a max_chars. |
| `_split_by_headings()` | *top_level* | `Parser / AST / Extração` | Divide o texto markdown/plano por cabeçalhos H1/H2. |
| `_split_pdf_pages()` | *top_level* | `Parser / AST / Extração` | Agrupa as páginas PDF em seções de até max_notes. |
| `inject_sibling_links()` | *top_level* | `Mutação / Escrita` | Cria links irmãos entre notas em note_paths. |
| `should_split()` | *top_level* | `Leitura / Consulta` | Retorna seções de título e conteúdo se o arquivo merecer divisão recursiva. |

#### Módulo: `synthesizer.py` (418 LOC)
**Responsabilidade**: Módulo que gera notas estruturadas do Obsidian a partir de texto bruto usando modelos de linguagem LLM.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_drop_placeholder_sections()` | *top_level* | `Parser / AST / Extração` | Remove seções de espaço reservado. |
| `_is_meeting_like()` | *top_level* | `Parser / AST / Extração` | Verifica se a nota é semelhante a uma reunião. |
| `_quote_frontmatter_fields()` | *top_level* | `Parser / AST / Extração` | Força a citação de campos de texto livre dentro do bloco de frontmatter inicial. |
| `_strip_think_tags()` | *top_level* | `Parser / AST / Extração` | Remove blocos de razão-modelo <think>...</think> antes de qualquer outro processamento. |
| `sanitize_note()` | *top_level* | `Mutação / Escrita` | Remove blocos de razão, grades de código, estrutura de prompt ecoado, bate-papo de encerramento e seções de espaço reservado. |
| `synthesize()` | *top_level* | `Cálculo / Algoritmo` | Gera uma nota estruturada do Obsidian a partir de texto bruto. |

#### Módulo: `vault.py` (1793 LOC)
**Responsabilidade**: Módulo responsável pela gestão do Obsidian Vault, operações de CRUD de notas, manipulação de frontmatter e arquivos, e busca semântica.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__init__()` | `VaultManager` | `Orquestração / Lifecycle` | Inicializa a instância do VaultManager. |
| `_adopt_legacy_collection()` | `VaultManager` | `Mutação / Escrita` | Renomeia uma coleção pré-derivação para o nome derivado do modelo, se compatível. |
| `_client_counts()` | `VaultManager` | `Leitura / Consulta` | {slug do cliente: documentos distintos} sobre toda a coleção. |
| `_close_client()` | `VaultManager` | `Orquestração / Lifecycle` | Fecha o cliente. |
| `_ensure_ready()` | `VaultManager` | `Orquestração / Lifecycle` | Garante que o VaultManager esteja pronto. |
| `_force_health_recompute()` | `VaultManager` | `Orquestração / Lifecycle` | Executa a passagem de saúde ignorando o cache de resumo, para popular os detalhes. |
| `_index_counts()` | `VaultManager` | `Leitura / Consulta` | (linhas, documentos distintos) na coleção. |
| `_index_state_path()` | `VaultManager` | `Leitura / Consulta` | Retorna o caminho do estado do índice. |
| `_init()` | `VaultManager` | `Orquestração / Lifecycle` | Inicializa o VaultManager. |
| `_load_index_state()` | `VaultManager` | `Leitura / Consulta` | Carrega o estado do índice. |
| `_note_row()` | `VaultManager` | `Leitura / Consulta` | Título/data/caminho/tamanho para uma nota, lendo apenas o cabeçalho de frontmatter. |
| `_paged_get()` | `VaultManager` | `Leitura / Consulta` | Busca com segurança todas as linhas correspondentes do ChromaDB em lotes para evitar limites de variáveis do SQLite. |
| `_parse_frontmatter()` | `VaultManager` | `Parser / AST / Extração` | Extrai pares chave:valor do primeiro bloco de frontmatter YAML. |
| `_read_disk_state()` | `VaultManager` | `Leitura / Consulta` | Realiza uma impressão digital barata do índice no disco: uma estatística do Chroma's sqlite. |
| `_reload_if_disk_changed()` | `VaultManager` | `Orquestração / Lifecycle` | Reabre a coleção quando outro processo escreve no índice. |
| `_save_index_state()` | `VaultManager` | `Mutação / Escrita` | Salva o estado do índice. |
| `_unindexed_notes()` | `VaultManager` | `Leitura / Consulta` | Notas que existem no disco e não têm linhas no índice. |
| `_update_index_state()` | `VaultManager` | `Mutação / Escrita` | Lê-modifica-escreve do estado do índice sob trava. |
| `classify_path()` | `VaultManager` | `Leitura / Consulta` | Retorna (kind, graph_name) para um caminho de nota relativo ao vault. |
| `classify_subkind()` | `VaultManager` | `Leitura / Consulta` | Retorna subkind ('transcript', 'chat', 'generated', ou 'curated') para uma nota. |
| `count_notes()` | `VaultManager` | `Leitura / Consulta` | Total de notas em uma pasta, ignorando qualquer limite de lista. |
| `delete_notes()` | `VaultManager` | `Mutação / Escrita` | Exclui notas do ChromaDB e do estado do índice incremental pelo caminho relativo ao vault. |
| `find_notes()` | `VaultManager` | `Leitura / Consulta` | Busca literal de título/caminho — sem embeddings, sem limite de semelhança. |
| `find_notes_by_stem()` | `VaultManager` | `Leitura / Consulta` | Encontra notas cujo nome de arquivo contém note_name (sem distinção entre maiúsculas e minúsculas). |
| `find_similar()` | `VaultManager` | `Leitura / Consulta` | Encontra notas semanticamente semelhantes à nota fornecida. |
| `get_health_summary()` | `VaultManager` | `Leitura / Consulta` | Varre o frontmatter do vault em busca de problemas de qualidade. Armazenado em cache por 5 minutos em ~/.delegation_core/vault_health.json. |
| `get_notes_needing_repair()` | `VaultManager` | `Leitura / Consulta` | Retorna [{path, content, quality_score}] ordenados por pontuação ascendente (pior primeiro). |
| `get_stats()` | `VaultManager` | `Leitura / Consulta` | Obtém estatísticas gerais. |
| `health_detail()` | `VaultManager` | `Leitura / Consulta` | Os detalhes por trás dos contagens de get_health_summary(), itemizados. |
| `inbox_status()` | `VaultManager` | `Leitura / Consulta` | Retorna o que está esperando na pasta _inbox do vault. |
| `index_note()` | `VaultManager` | `Mutação / Escrita` | Insere ou atualiza conteúdo no ChromaDB. Retorna True quando as linhas foram inseridas. |
| `list_directories()` | `VaultManager` | `Leitura / Consulta` | Cada diretório sob um diretório configurado que mantém notas. |
| `list_notes()` | `VaultManager` | `Leitura / Consulta` | Lista notas em uma pasta (incluindo subpastas) ordenadas do mais recente para o mais antigo por mtime. |
| `list_notes_in()` | `VaultManager` | `Leitura / Consulta` | Notas diretamente dentro de um diretório — não seus subdiretórios. |
| `note_links()` | `VaultManager` | `Leitura / Consulta` | Links wikiliques de entrada e saída para uma nota. |
| `note_metadata()` | `VaultManager` | `Leitura / Consulta` | Constrói a linha de metadados para uma nota de vault, incluindo seu escopo de pesquisa e subkind. |
| `reindex_vault()` | `VaultManager` | `Mutação / Escrita` | Reindexa notas markdown nos diretórios de vault configurados. |
| `resolvable_link_targets()` | `VaultManager` | `Leitura / Consulta` | Cada nome a que um `[[wikilink]]` neste vault pode resolver-se legitimamente. |
| `search()` | `VaultManager` | `Leitura / Consulta` | Busca semântica, opcionalmente limitada a um tipo específico de conteúdo indexado. |
| `stamp_indexed()` | `VaultManager` | `Mutação / Escrita` | Registra que essas notas estão atualizadas no índice. Retorna quantas. |
| `update_note()` | `VaultManager` | `Mutação / Escrita` | Anexa conteúdo a uma nota existente e a reindexa. |
| `warm_up()` | `VaultManager` | `Orquestração / Lifecycle` | Inicia o carregamento do modelo BGE em um thread em segundo plano antes da primeira chamada de ferramenta. |

### Domínio: `Core & Daemon`
> **Módulos**: 11 | **Funções**: 103 | **LOC**: 3,109

#### Módulo: `__init__.py` (22 LOC)
**Responsabilidade**: Bootstrap e inicialização do servidor MCP local.

*Módulo de constantes, tipos ou declarações puras sem funções executáveis.*

#### Módulo: `__main__.py` (2 LOC)
**Responsabilidade**: Ponto de entrada principal do aplicativo.

*Módulo de constantes, tipos ou declarações puras sem funções executáveis.*

#### Módulo: `capabilities.py` (199 LOC)
**Responsabilidade**: Determina as capacidades do servidor derivadas do código.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `describe()` | *top_level* | `Handler MCP / Endpoint` | Monta o relatório de capacidades fornecido a um cliente conectado. |

#### Módulo: `config.py` (697 LOC)
**Responsabilidade**: Módulo de configuração do sistema, responsável por armazenar e gerenciar as configurações do usuário em ~/.delegation_core/config.json.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `chroma_path()` | `Config` | `Leitura / Consulta` | Retorna o caminho do Chroma. |
| `collection_name()` | `Config` | `Leitura / Consulta` | Retorna o nome da coleção do ChromaDB. |
| `embed_log_path()` | `Config` | `Leitura / Consulta` | Retorna o caminho do log de embeddings. |
| `ensure_server_token()` | `Config` | `Validação / Segurança` | Retorna o token bearer, gerando e persistindo um na primeira chamada. |
| `graphs_dir()` | `Config` | `Leitura / Consulta` | Retorna o diretório dos gráficos. |
| `graphs_registry_path()` | `Config` | `Leitura / Consulta` | Retorna o caminho do registro de gráficos. |
| `index_dir()` | `Config` | `Leitura / Consulta` | Retorna o diretório do índice em uso. |
| `is_agent_mode()` | `Config` | `Leitura / Consulta` | Indica se o modo agente está ativo. |
| `is_configured()` | `Config` | `Leitura / Consulta` | Indica se a configuração está pronta. |
| `is_cpu_budget()` | `Config` | `Leitura / Consulta` | Indica se há um orçamento de CPU. |
| `is_hybrid_mode()` | `Config` | `Leitura / Consulta` | Indica se o modo híbrido está ativo. |
| `llama_dir()` | `Config` | `Leitura / Consulta` | Retorna o diretório do Llama. |
| `llama_log_path()` | `Config` | `Leitura / Consulta` | Retorna o caminho do log do Llama. |
| `llama_url()` | `Config` | `Leitura / Consulta` | Retorna a URL do Llama. |
| `load()` | `Config` | `Leitura / Consulta` | Carrega a configuração. |
| `local_index_fallback_allowed()` | `Config` | `Leitura / Consulta` | Indica se um comando pode escrever o índice neste processo. |
| `log_path()` | `Config` | `Leitura / Consulta` | Retorna o caminho do log. |
| `modelo_no_pedido()` | `Config` | `Leitura / Consulta` | Retorna o modelo especificado no pedido ao servidor local. |
| `models_dir()` | `Config` | `Leitura / Consulta` | Retorna o diretório dos modelos. |
| `motor_e_mlx()` | `Config` | `Leitura / Consulta` | Retorna o motor e MLX configurados. |
| `processes_path()` | `Config` | `Leitura / Consulta` | Retorna o caminho dos processos. |
| `route()` | `Config` | `Orquestração / Lifecycle` | Decide onde uma chamada de geração deve ser executada. |
| `save()` | `Config` | `Mutação / Escrita` | Persiste a configuração de forma atômica. |
| `server_url()` | `Config` | `Leitura / Consulta` | Retorna a URL do endpoint MCP do servidor local. |
| `sqlite_path()` | `Config` | `Leitura / Consulta` | Retorna o caminho do índice SQLite. |
| `usa_sqlite()` | `Config` | `Leitura / Consulta` | Indica se o SQLite está sendo usado. |
| `uses_local_model()` | `Config` | `Leitura / Consulta` | Indica se o modelo local está sendo usado. |
| `vault()` | `Config` | `Leitura / Consulta` | Retorna o caminho do Vault. |

#### Módulo: `daemon.py` (371 LOC)
**Responsabilidade**: Módulo responsável por comunicação com o daemon e execução de tarefas MCP.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_build_client()` | *top_level* | `Utilitário / Helper` | Constrói um cliente para comunicação com o daemon. |
| `_is_connection_error()` | *top_level* | `Validação / Segurança` | Verifica se esta exceção ou algo que a embrulha é uma falha de conexão. |
| `_is_timeout()` | *top_level* | `Validação / Segurança` | Verifica se uma falha ou algo que a embrulha foi um tempo esgotado. |
| `_payload()` | *top_level* | `Parser / AST / Extração` | Desempacota um CallToolResult para o dicionário retornado pela ferramenta. |
| `_run()` | *top_level* | `Orquestração / Lifecycle` | Executa uma corrotina de daemon, mapeando falhas de transporte para erros. |
| `call_tool()` | *top_level* | `Handler MCP / Endpoint` | Chama uma ferramenta MCP no daemon em execução e retorna seu resultado analisado. |
| `is_listening()` | *top_level* | `Leitura / Consulta` | Verifica se algo aceita conexões na porta configurada. |
| `next_poll_wait()` | *top_level* | `Cálculo / Algoritmo` | Determina quanto tempo esperar antes de sondar novamente ou indica que o trabalho está concluído. |
| `submit_and_wait()` | *top_level* | `Orquestração / Lifecycle` | Chama uma ferramenta de fundo e sondra task_status até que o trabalho seja concluído. |

#### Módulo: `engine.py` (711 LOC)
**Responsabilidade**: O módulo engine.py gerencia o subprocesso llama.cpp e a inferência.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__aenter__()` | `DelegationEngine` | `Orquestração / Lifecycle` | Método de entrada para gerenciamento de contexto assíncrono. |
| `__aexit__()` | `DelegationEngine` | `Orquestração / Lifecycle` | Método de saída para gerenciamento de contexto assíncrono. |
| `__init__()` | `DelegationEngine` | `Orquestração / Lifecycle` | Inicializa a instância do DelegationEngine. |
| `_answer_of()` | `DelegationEngine` | `Leitura / Consulta` | A resposta do modelo, e nunca uma string vazia silenciosa. |
| `_async_client()` | `DelegationEngine` | `Handler MCP / Endpoint` | Cria um cliente assíncrono. |
| `_extractive_fallback()` | `DelegationEngine` | `Cálculo / Algoritmo` | Substituição determinística, sem computação usada no modo agente para o fundo. |
| `_invoke_now()` | `DelegationEngine` | `Handler MCP / Endpoint` | Corpo da invocação(), executado com o portão de modelo local já mantido. |
| `_is_healthy()` | `DelegationEngine` | `Validação / Segurança` | Verificação de saúde síncrona usada durante a sondagem de inicialização do subprocesso. |
| `_queued()` | `DelegationEngine` | `Orquestração / Lifecycle` | Manter o portão de modelo local por toda a duração do bloco. |
| `_shutdown()` | `DelegationEngine` | `Orquestração / Lifecycle` | Encerra o subprocesso. |
| `_start()` | `DelegationEngine` | `Orquestração / Lifecycle` | Inicia o subprocesso. |
| `_start_locked()` | `DelegationEngine` | `Orquestração / Lifecycle` | Inicia o subprocesso com bloqueio. |
| `_start_mlx()` | `DelegationEngine` | `Orquestração / Lifecycle` | Inicia o mlx_lm.server com os argumentos dele e não os do llama.cpp. |
| `aclose()` | `DelegationEngine` | `Orquestração / Lifecycle` | Fecha a instância de forma assíncrona. |
| `budget()` | `DelegationEngine` | `Cálculo / Algoritmo` | Retorna o limite máximo de tokens efetivo para uma tarefa, respeitando o modo de orçamento. |
| `calibrate()` | `DelegationEngine` | `Cálculo / Algoritmo` | Mede a taxa de tokens por segundo de uma chamada direta à API que lê tokens de conclusão. |
| `check_health()` | `DelegationEngine` | `Validação / Segurança` | Verifica a saúde do subprocesso. |
| `ensure_running()` | `DelegationEngine` | `Orquestração / Lifecycle` | Garante que o subprocesso esteja em execução. |
| `invoke()` | `DelegationEngine` | `Handler MCP / Endpoint` | Chamada assíncrona para llama.cpp /v1/chat/completions. A tarefa seleciona o limite de orçamento. |
| `_compute_budgets()` | *top_level* | `Cálculo / Algoritmo` | Computa os limites de tokens por tarefa a partir da taxa de throughput medida e do tempo de timeout do MCP. |
| `_detached_popen_kwargs()` | *top_level* | `Configuração / Setup` | Argumentos para subprocesso detached. |
| `_gate()` | *top_level* | `Orquestração / Lifecycle` | Retorna o portão de processo, dimensionado pelo primeiro chamador que precisar dele. |
| `_llama_env()` | *top_level* | `Configuração / Setup` | Ambiente do processo do modelo, conforme o dispositivo pedido. |
| `_reset_queue_for_tests()` | *top_level* | `Teste / Debug` | Descarta o portão para que um teste possa re-armá-lo em uma concorrência diferente. |
| `llama_device()` | *top_level* | `Configuração / Setup` | Onde o modelo local deve rodar. Valor desconhecido vira "auto" com aviso. |
| `queue_stats()` | *top_level* | `Monitoramento / Telemetria` | Instantâneo da fila do modelo local, para heartbeat()/dashboards. |

#### Módulo: `locking.py` (165 LOC)
**Responsabilidade**: Módulo responsável pela gestão de travas exclusivas entre processos.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_destravar()` | *top_level* | `Validação / Segurança` | Libera uma trava. |
| `_tentar_travar()` | *top_level* | `Validação / Segurança` | Tenta obter uma trava de forma não bloqueante. |
| `arquivo_travado()` | *top_level* | `Validação / Segurança` | Segura uma trava exclusiva enquanto um bloco roda. |
| `ler_modificar_escrever()` | *top_level* | `Validação / Segurança` | Executa um ciclo completo sob uma trava, que é o ponto deste módulo. |

#### Módulo: `procs.py` (39 LOC)
**Responsabilidade**: Módulo responsável por processos filhos que não abrem janela de console no Windows.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_e_windows()` | *top_level* | `Validação / Segurança` | Verifica se o sistema é Windows. |
| `sem_janela()` | *top_level* | `Utilitário / Helper` | Retorna kwargs para subprocess que impedem o Windows de abrir um novo console. |

#### Módulo: `service.py` (590 LOC)
**Responsabilidade**: Módulo responsável por instalar e gerenciar o serviço HTTP daemon como um serviço de fundo per-usuário.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_abrir_launcher()` | *top_level* | `Orquestração / Lifecycle` | Executa o .cmd da pasta Startup sem abrir janela. |
| `_e_o_daemon()` | *top_level* | `Utilitário / Helper` | Verifica se o processo é o daemon. |
| `_esperar_fim()` | *top_level* | `Orquestração / Lifecycle` | Espera o término do daemon. |
| `_executable()` | *top_level* | `Utilitário / Helper` | Retorna o caminho absoluto para o script de console instalado. |
| `_parar_processos_do_daemon()` | *top_level* | `Orquestração / Lifecycle` | Para os processos do daemon. |
| `_port_answers()` | *top_level* | `Orquestração / Lifecycle` | Verifica se algo está respondendo na porta configurada. |
| `_processos_candidatos()` | *top_level* | `Utilitário / Helper` | Identifica processos candidatos. |
| `_run()` | *top_level* | `Orquestração / Lifecycle` | Executa o daemon. |
| `_windows_interpreter()` | *top_level* | `Utilitário / Helper` | Retorna o interpretador Python que executa o daemon no Windows e se ele não tem console. |
| `_windows_launcher_text()` | *top_level* | `Utilitário / Helper` | Retorna o texto do .cmd que a pasta Startup executa no logon. |
| `_windows_run_command()` | *top_level* | `Utilitário / Helper` | Retorna o comando do daemon Windows sem o wrapper de script de console. |
| `install()` | *top_level* | `Orquestração / Lifecycle` | Registra o daemon para iniciar no login. |
| `is_up()` | *top_level* | `Orquestração / Lifecycle` | Verifica se o daemon está respondendo na porta. |
| `launchd_plist_text()` | *top_level* | `Utilitário / Helper` | Gera o texto do plist launchd. |
| `restart()` | *top_level* | `Orquestração / Lifecycle` | Reinicia o daemon. |
| `start()` | *top_level* | `Orquestração / Lifecycle` | Inicia o daemon. |
| `status()` | *top_level* | `Orquestração / Lifecycle` | Relata o status do serviço e se a porta está respondendo. |
| `stop()` | *top_level* | `Orquestração / Lifecycle` | Para o daemon, deixando sua регистраção em vigor. |
| `systemd_unit_text()` | *top_level* | `Utilitário / Helper` | Gera o texto da unidade systemd. |
| `uninstall()` | *top_level* | `Orquestração / Lifecycle` | Desinstala o daemon. |
| `uninstall_llama_autostart()` | *top_level* | `Orquestração / Lifecycle` | Remove a entrada de autostart do llama.cpp registrada pelo wizard. |
| `wait_until_down()` | *top_level* | `Orquestração / Lifecycle` | Espera até que o daemon pare de responder. |

#### Módulo: `stdio_nulo.py` (109 LOC)
**Responsabilidade**: Módulo que redireciona stdout, stderr e stdin para destinos reais se eles forem None.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `garantir_stdio()` | *top_level* | `Orquestração / Lifecycle` | Troca por um destino real o stdout, stderr e stdin que forem None. |

#### Módulo: `tracker.py` (204 LOC)
**Responsabilidade**: Módulo responsável por registrar e gerenciar processos persistentes.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__init__()` | `ProcessTracker` | `Orquestração / Lifecycle` | Inicializa a instância de ProcessTracker. |
| `_read()` | `ProcessTracker` | `Leitura / Consulta` | Lê os processos registrados do arquivo, ou retorna uma lista vazia se o arquivo não existir. |
| `_write()` | `ProcessTracker` | `Mutação / Escrita` | Escreve os processos registrados para o arquivo. |
| `create()` | `ProcessTracker` | `Mutação / Escrita` | Cria um novo registro de processo. |
| `get()` | `ProcessTracker` | `Leitura / Consulta` | Obtém detalhes de um processo específico. |
| `list_processes()` | `ProcessTracker` | `Leitura / Consulta` | Lista todos os processos registrados. |
| `summary()` | `ProcessTracker` | `Leitura / Consulta` | Fornece um resumo compacto dos processos ativos. |
| `update()` | `ProcessTracker` | `Mutação / Escrita` | Atualiza um registro de processo existente. |
| `_find_process()` | *top_level* | `Leitura / Consulta` | Encontra um processo por ID exato, ou por correspondência de prefixo. |
| `_now()` | *top_level* | `Utilitário / Helper` | Obtém a hora atual. |

### Domínio: `Hooks & Integrations`
> **Módulos**: 9 | **Funções**: 84 | **LOC**: 2,446

#### Módulo: `clients.py` (566 LOC)
**Responsabilidade**: Módulo responsável por apontar clientes MCP para o daemon HTTP.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_codex_hook_command()` | *top_level* | `Utilitário / Helper` | Constrói um comando de hook confiável e portátil. |
| `_codex_hook_groups_without_ours()` | *top_level* | `Utilitário / Helper` | Função auxiliar para grupos de hooks do Codex sem os nossos. |
| `_e_nosso()` | *top_level* | `Utilitário / Helper` | Registro escrito por nós: o comando novo, ou um dos scripts copiados. |
| `_e_nosso_codex()` | *top_level* | `Utilitário / Helper` | Reconhece tanto os hooks atuais do Codex quanto os genéricos de pré-lançamento. |
| `_gravar_settings()` | *top_level* | `Mutação / Escrita` | Função auxiliar para gravar configurações. |
| `_ler_settings()` | *top_level* | `Leitura / Consulta` | Função auxiliar para ler configurações. |
| `_sem_os_nossos()` | *top_level* | `Utilitário / Helper` | Os grupos de um evento sem os nossos registros. Hooks de outros ficam. |
| `antigravity_entry()` | *top_level* | `Leitura / Consulta` | Obtém o valor mcpServers do ~/.gemini/config/mcp_config.json para o daemon. |
| `claude_code_entry()` | *top_level* | `Leitura / Consulta` | Obtém o valor mcpServers do ~/.claude.json apontando para o daemon. |
| `claude_desktop_config_path()` | *top_level* | `Utilitário / Helper` | Obtém o caminho da configuração do Claude Desktop. |
| `claude_desktop_entry()` | *top_level* | `Leitura / Consulta` | Obtém o valor do claude_desktop_config.json, sempre stdio e nunca uma URL. |
| `codex_block()` | *top_level* | `Leitura / Consulta` | Obtém a tabela ~/.codex/config.toml apontando para o daemon. |
| `entry_summary()` | *top_level* | `Leitura / Consulta` | Tudo que um cliente precisa, para superfícies que este módulo não escreve. |
| `hook_executable()` | *top_level* | `Leitura / Consulta` | O `delegation-core-hook` do venv que está rodando agora. |
| `install_antigravity()` | *top_level* | `Mutação / Escrita` | Aponta Antigravity / o CLI Gemini para o daemon. |
| `install_claude_code()` | *top_level* | `Mutação / Escrita` | Reescreve a entrada delegation-core em ~/.claude.json para o formulário HTTP. |
| `install_claude_desktop()` | *top_level* | `Mutação / Escrita` | Aponta o Claude Desktop para o daemon HTTP em claude_desktop_config.json. |
| `install_codex()` | *top_level* | `Mutação / Escrita` | Anexa (ou relata) a tabela delegation-core em ~/.codex/config.toml. |
| `register_codex_session_hook()` | *top_level* | `Mutação / Escrita` | Registra o pequeno Codex SessionEnd dispatcher sem tocar no TOML. |
| `register_session_hooks()` | *top_level* | `Mutação / Escrita` | Registra `delegation-core-hook` nos eventos de sessão do Claude Code. |
| `unregister_codex_session_hook()` | *top_level* | `Mutação / Escrita` | Desregistra o hook de sessão do Codex. |
| `unregister_session_hooks()` | *top_level* | `Mutação / Escrita` | Tira os nossos registros de sessão; os de terceiros ficam. |

#### Módulo: `graph/google_workspace.py` (238 LOC)
**Responsabilidade**: Módulo que fornece suporte opcional para exportação de atalhos do Google Workspace.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_extract_file_id_from_url()` | *top_level* | `Parser / AST / Extração` | Extrai um ID de arquivo do Google Drive de URLs comuns de Docs/Drive. |
| `_extract_resource_key()` | *top_level* | `Utilitário / Helper` | Função interna para extração de chave de recurso. |
| `_run_gws_export()` | *top_level* | `Utilitário / Helper` | Função interna para execução da exportação do Google Workspace. |
| `_safe_yaml_str()` | *top_level* | `Utilitário / Helper` | Função interna para processamento seguro de strings YAML. |
| `_sidecar_path()` | *top_level* | `Utilitário / Helper` | Função interna para determinar o caminho do sidecar. |
| `_with_frontmatter()` | *top_level* | `Utilitário / Helper` | Função interna para adicionar frontmatter. |
| `convert_google_workspace_file()` | *top_level* | `Mutação / Escrita` | Exporta um atalho do Google Workspace para um sidecar Markdown. |
| `google_workspace_enabled()` | *top_level* | `Validação / Segurança` | Retorna True quando a exportação de atalhos do Google Workspace estiver habilitada. |
| `read_google_shortcut()` | *top_level* | `Leitura / Consulta` | Lê um atalho .gdoc/.gsheet/.gslides e retorna metadados de exportação. |

#### Módulo: `graph_hook.py` (151 LOC)
**Responsabilidade**: Módulo responsável por instalar e desinstalar hooks de git para atualização automática do gráfico.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_git_root()` | *top_level* | `Utilitário / Helper` | Percorre para cima para encontrar o repositório contendo .git (diretório ou arquivo, para worktrees). |
| `_hook_script()` | *top_level* | `Utilitário / Helper` | Função não documentada. |
| `_hooks_dir()` | *top_level* | `Utilitário / Helper` | Retorna o diretório de hooks do git, respeitando core.hooksPath se definido (por exemplo, Husky). |
| `install()` | *top_level* | `Orquestração / Lifecycle` | Instala um hook post-commit que reconstrói o gráfico de código (no diretório atual). |
| `status()` | *top_level* | `Leitura / Consulta` | Função não documentada. |
| `uninstall()` | *top_level* | `Orquestração / Lifecycle` | Remove o hook post-commit do delegation-core (deixa outros hooks intactos). |

#### Módulo: `graph_hook_rebuild.py` (168 LOC)
**Responsabilidade**: Módulo responsável por reconstruir o grafo de conhecimento após um commit no Git.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_apply_resource_limits()` | *top_level* | `Utilitário / Helper` | Aplica limites de recursos (nice e memória) para evitar que a reconstrução em segundo plano sobrecarregue o sistema. |
| `_lock_is_stale()` | *top_level* | `Validação / Segurança` | Verifica se um lock está obsoleto com base na idade ou PID do proprietário. |
| `main()` | *top_level* | `Orquestração / Lifecycle` | Função principal que coordena o processo de reconstrução do grafo. |

#### Módulo: `hooks/__init__.py` (11 LOC)
**Responsabilidade**: Pacote de hooks de sessão do Claude Code.

*Módulo de constantes, tipos ou declarações puras sem funções executáveis.*

#### Módulo: `hooks/entrada.py` (233 LOC)
**Responsabilidade**: Processo por evento de sessão do Claude Code, incluindo funções de início e fim de sessão.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_detached_popen_kwargs()` | *top_level* | `Utilitário / Helper` | Retorna argumentos para subprocessos desanexados. |
| `_inside_payload_dir()` | *top_level* | `Utilitário / Helper` | Verifica se um caminho está dentro do diretório de payload. |
| `_is_windows()` | *top_level* | `Utilitário / Helper` | Verifica se o sistema operacional é Windows. |
| `_passo()` | *top_level* | `Utilitário / Helper` | Função auxiliar. |
| `_payload_dir()` | *top_level* | `Utilitário / Helper` | Função auxiliar para obter o diretório de payload. |
| `_sweep_stale_payloads()` | *top_level* | `Utilitário / Helper` | Limpa payloads obsoletos. |
| `codex_session_end()` | *top_level* | `Handler MCP / Endpoint` | Retorna do hook SessionEnd do Codex antes que o trabalho de exportação comece. |
| `codex_session_start()` | *top_level* | `Handler MCP / Endpoint` | Fornece o protocolo Delegation Core junto com o resumo da sessão usual. |
| `main()` | *top_level* | `Orquestração / Lifecycle` | Função principal que coordena o processo de sessão. |
| `session_end()` | *top_level* | `Handler MCP / Endpoint` | Função chamada no fim de uma sessão. |
| `session_end_file()` | *top_level* | `Handler MCP / Endpoint` | Função chamada no fim de uma sessão para manipular arquivos. |
| `session_start()` | *top_level* | `Handler MCP / Endpoint` | Função chamada no início de uma sessão. |

#### Módulo: `hooks/llama_session_stop.py` (215 LOC)
**Responsabilidade**: Este módulo contém funções para lidar com o encerramento de sessões do Claude Code, incluindo verificações de status, parada de processos e operações de configuração.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `find_pid()` | *top_level* | `Leitura / Consulta` | Encontra o PID de um processo com base em seu comando de linha. |
| `http_json()` | *top_level* | `Leitura / Consulta` | Realiza uma solicitação GET e analisa JSON, retornando None se falhar. |
| `is_busy()` | *top_level* | `Leitura / Consulta` | Verifica se o endpoint /slots está respondendo. |
| `load_config()` | *top_level* | `Utilitário / Helper` | Carrega a configuração. |
| `log()` | *top_level* | `Utilitário / Helper` | Registra mensagens de log. |
| `main()` | *top_level* | `Orquestração / Lifecycle` | Função principal que coordena o encerramento da sessão. |
| `other_session_fresh()` | *top_level* | `Leitura / Consulta` | Verifica se há outras sessões MCP ativas. |
| `stop()` | *top_level* | `Mutação / Escrita` | Envia sinais SIGTERM e SIGKILL para parar um processo. |

#### Módulo: `hooks/session_export.py` (512 LOC)
**Responsabilidade**: Este módulo contém funções para exportar transcrições de sessões do Claude Code, incluindo manipulação de YAML, configuração, captura de transcrições e formatação de texto.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_capture_markers()` | *top_level* | `Parser / AST / Extração` | Função interna para captura de marcadores. |
| `_detached_popen_kwargs()` | *top_level* | `Utilitário / Helper` | Retorna argumentos apropriados para iniciar um processo em segundo plano. |
| `_format_markdown()` | *top_level* | `Utilitário / Helper` | Formata o texto em Markdown. |
| `_load_config()` | *top_level* | `Utilitário / Helper` | Carrega a configuração. |
| `_manual_capture_requested()` | *top_level* | `Leitura / Consulta` | Verifica se uma captura manual foi solicitada. |
| `_parse_transcript()` | *top_level* | `Parser / AST / Extração` | Extrai turnos de texto do usuário e assistente da transcrição JSONL. |
| `_redigir()` | *top_level* | `Validação / Segurança` | Remove strings que parecem credenciais. |
| `_resolve_sessions_dir()` | *top_level* | `Leitura / Consulta` | Seleciona o diretório de sessões do vault com base em sua configuração. |
| `_response_item_message()` | *top_level* | `Parser / AST / Extração` | Encontra a mensagem do usuário/assistente aninhada em um item de resposta Codex. |
| `_session_date()` | *top_level* | `Leitura / Consulta` | Obtém a data de início da sessão a partir do primeiro timestamp. |
| `_text_content()` | *top_level* | `Parser / AST / Extração` | Extrai texto de blocos de conteúdo de mensagens Claude e Codex. |
| `_topic()` | *top_level* | `Parser / AST / Extração` | Extrai o primeiro texto real digitado pelo usuário, sem marcação do Claude Code. |
| `_trigger_reindex()` | *top_level* | `Orquestração / Lifecycle` | Dispara o comando `delegation-core reindex` como um processo em segundo plano. |
| `_yaml_quote_scalar()` | *top_level* | `Parser / AST / Extração` | Duplica aspas em uma string para uso seguro como valor escalar YAML. |
| `capture_permitted()` | *top_level* | `Validação / Segurança` | Verifica se a política atual permite a captura da transcrição. |
| `main()` | *top_level* | `Orquestração / Lifecycle` | Exporta a transcrição da sessão que terminou. |
| `transcript_mode()` | *top_level* | `Leitura / Consulta` | Lê um modo seguro de JSON, preservando o padrão antigo. |

#### Módulo: `hooks/session_start_brief.py` (352 LOC)
**Responsabilidade**: Este módulo contém funções para lidar com o início de sessões do Claude Code, incluindo disparo de manutenção, reindexação e operações de configuração.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_detached_popen_kwargs()` | *top_level* | `Utilitário / Helper` | Retorna argumentos apropriados para iniciar um processo em segundo plano. |
| `_load_json()` | *top_level* | `Leitura / Consulta` | Carrega dados JSON. |
| `_marca_do_inbox()` | *top_level* | `Leitura / Consulta` | Imprime uma lista dos arquivos no inbox com seus nomes e tempos de modificação. |
| `_separar_lotes()` | *top_level* | `Parser / AST / Extração` | Divide as notas entre corridas contíguas e escrita avulsa. |
| `_trigger_maintenance()` | *top_level* | `Orquestração / Lifecycle` | Dispara o comando `delegation-core maintain` como um processo em segundo plano. |
| `_trigger_reindex()` | *top_level* | `Orquestração / Lifecycle` | Dispara o comando `delegation-core reindex` como um processo em segundo plano. |
| `main()` | *top_level* | `Orquestração / Lifecycle` | Função principal que coordena o início da sessão. |

### Domínio: `Search & Embeddings`
> **Módulos**: 7 | **Funções**: 122 | **LOC**: 2,578

#### Módulo: `avaliacao.py` (107 LOC)
**Responsabilidade**: Avaliação de busca com perguntas com resposta conhecida e medidas por escopo.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `avaliar()` | *top_level* | `Cálculo / Algoritmo` | Avalia a precisão da busca. |
| `buscador_do_daemon()` | *top_level* | `Leitura / Consulta` | Busca pelo daemon em execução, sem abrir o índice em um segundo processo. |
| `carregar()` | *top_level* | `Leitura / Consulta` | Carrega o arquivo de consultas, exigindo a presença de `esperado`. |
| `posicao_do_acerto()` | *top_level* | `Cálculo / Algoritmo` | Determina a posição do primeiro caminho que contém o esperado. |

#### Módulo: `classifier.py` (93 LOC)
**Responsabilidade**: Módulo responsável por classificar documentos usando um modelo LLM.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `classify()` | *top_level* | `Mutação / Escrita` | Classifica um documento em uma pasta usando uma única chamada ao llama.cpp. |
| `looks_like_session()` | *top_level* | `Validação / Segurança` | Determina se um arquivo é claramente um log de sessão. |

#### Módulo: `embed_llama.py` (397 LOC)
**Responsabilidade**: Implementa a geração de embeddings usando o modelo LLaMA, servindo como uma alternativa ao sentence-transformers.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__init__()` | `EmbedServer` | `Orquestração / Lifecycle` | Inicializa o servidor de embeddings. |
| `_start()` | `EmbedServer` | `Orquestração / Lifecycle` | Inicia o servidor de embeddings. |
| `base()` | `EmbedServer` | `Handler MCP / Endpoint` | Define o endpoint base para o servidor de embeddings. |
| `ensure()` | `EmbedServer` | `Orquestração / Lifecycle` | Garante que o servidor de embeddings esteja em execução. |
| `healthy()` | `EmbedServer` | `Validação / Segurança` | Verifica se o servidor de embeddings está saudável. |
| `shutdown()` | `EmbedServer` | `Orquestração / Lifecycle` | Encerra o servidor de embeddings. |
| `__call__()` | `LlamaCppEmbeddingFunction` | `Handler MCP / Endpoint` | Executa a função de embedding. |
| `__init__()` | `LlamaCppEmbeddingFunction` | `Orquestração / Lifecycle` | Inicializa a função de embedding LLaMA. |
| `_lote()` | `LlamaCppEmbeddingFunction` | `Handler MCP / Endpoint` | Processa um lote de solicitações de embedding. |
| `_pedir()` | `LlamaCppEmbeddingFunction` | `Handler MCP / Endpoint` | Realiza uma solicitação de embedding. |
| `build_from_config()` | `LlamaCppEmbeddingFunction` | `Orquestração / Lifecycle` | Constrói a função de embedding a partir da configuração. |
| `default_space()` | `LlamaCppEmbeddingFunction` | `Leitura / Consulta` | Retorna o espaço padrão para a função de embedding. |
| `get_config()` | `LlamaCppEmbeddingFunction` | `Leitura / Consulta` | Obtém a configuração da função de embedding. |
| `is_legacy()` | `LlamaCppEmbeddingFunction` | `Validação / Segurança` | Verifica se a função de embedding é legada. |
| `name()` | `LlamaCppEmbeddingFunction` | `Leitura / Consulta` | Retorna o nome da função de embedding. |
| `supported_spaces()` | `LlamaCppEmbeddingFunction` | `Leitura / Consulta` | Retorna os espaços suportados pela função de embedding. |
| `_detached()` | *top_level* | `Orquestração / Lifecycle` | Executa o servidor LLaMA em segundo plano. |
| `_llama_server_do_modelo()` | *top_level* | `Leitura / Consulta` | Retorna o servidor LLaMA associado ao modelo. |
| `_normalizar()` | *top_level* | `Utilitário / Helper` | Normaliza o caminho do servidor LLaMA. |
| `achar_llama_server()` | *top_level* | `Leitura / Consulta` | Localiza o binário do servidor LLaMA. |
| `comando_do_servidor()` | *top_level* | `Orquestração / Lifecycle` | Gera o comando para iniciar o servidor LLaMA. |
| `configurado()` | *top_level* | `Validação / Segurança` | Verifica se o servidor LLaMA está configurado corretamente. |
| `gguf_padrao()` | *top_level* | `Leitura / Consulta` | Retorna o caminho padrão do arquivo GGUF. |
| `preparar()` | *top_level* | `Orquestração / Lifecycle` | Prepara o servidor LLaMA para execução. |
| `servidor_para()` | *top_level* | `Orquestração / Lifecycle` | Inicia o servidor LLaMA. |
| `url_do_gguf()` | *top_level* | `Leitura / Consulta` | Retorna a URL do arquivo GGUF. |

#### Módulo: `embeddings.py` (636 LOC)
**Responsabilidade**: Módulo responsável pela criação de funções de embedding BGE e utilitários de chunking de texto.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__call__()` | `EmbedderSentenceTransformer` | `Handler MCP / Endpoint` | Chama o embedder para processar os documentos. |
| `__init__()` | `EmbedderSentenceTransformer` | `Orquestração / Lifecycle` | Inicializa o EmbedderSentenceTransformer. |
| `_encode()` | `EmbedderSentenceTransformer` | `Cálculo / Algoritmo` | Codifica os documentos usando o modelo de embedding. |
| `default_space()` | `EmbedderSentenceTransformer` | `Leitura / Consulta` | Retorna o espaço padrão do embedder. |
| `embed_documents()` | `EmbedderSentenceTransformer` | `Mutação / Escrita` | Embora os documentos usando o modelo de embedding. |
| `embed_query()` | `EmbedderSentenceTransformer` | `Mutação / Escrita` | Embora a consulta usando o modelo de embedding. |
| `name()` | `EmbedderSentenceTransformer` | `Leitura / Consulta` | Retorna o nome do embedder. |
| `__init__()` | `_Carga` | `Orquestração / Lifecycle` | Inicializa a carga do embedder. |
| `_rodar()` | `_Carga` | `Orquestração / Lifecycle` | Executa a carga do embedder. |
| `_effective_max_seq_length()` | *top_level* | `Cálculo / Algoritmo` | Resolve o limite de comprimento da sequência a aplicar. |
| `_importar_sentence_transformers()` | *top_level* | `Utilitário / Helper` | Importa o módulo sentence-transformers. |
| `_is_out_of_memory()` | *top_level* | `Validação / Segurança` | Verifica se houve uma falha de memória no acelerador. |
| `_model_is_cached()` | *top_level* | `Validação / Segurança` | Verifica se os pesos do modelo já estão no disco. |
| `carregar_com_prazo()` | *top_level* | `Orquestração / Lifecycle` | Executa a função 'fabrica()' com prazo. |
| `chunk_text()` | *top_level* | `Parser / AST / Extração` | Divide o texto em chunks sobrepostos para uma cobertura melhor do embedding em documentos longos. |
| `collection_name_for()` | *top_level* | `Leitura / Consulta` | Retorna o nome da coleção do ChromaDB que armazena os vetores do modelo. |
| `construir_embedding_function()` | *top_level* | `Handler MCP / Endpoint` | Constrói a função de embedding do backend configurado. |
| `detect_device()` | *top_level* | `Leitura / Consulta` | Detecta e retorna o dispositivo disponível ('cuda', 'mps', ou 'cpu'). |
| `effective_chunk_chars()` | *top_level* | `Cálculo / Algoritmo` | Limita um chunk de caracteres ao que a janela de token do modelo pode conter. |
| `explicar_falha_de_import()` | *top_level* | `Utilitário / Helper` | Explica a falha de importação do BGE sem esconder a causa. |
| `make_bge_embedding_function()` | *top_level* | `Handler MCP / Endpoint` | Constrói a função de embedding BGE (um callable simples sobre sentence-transformers). |
| `prefer_offline()` | *top_level* | `Orquestração / Lifecycle` | Habilita o modo offline do HF, mas apenas quando os pesos estão realmente armazenados. |
| `profile_for()` | *top_level* | `Leitura / Consulta` | Retorna o perfil de recuperação para um modelo de embedding. |
| `resolver_backend()` | *top_level* | `Leitura / Consulta` | Resolve o backend ('torch' ou 'llamacpp') com base na configuração. |
| `resolver_dispositivo()` | *top_level* | `Leitura / Consulta` | Traduz a preferência de configuração no dispositivo a ser usado. |
| `usa_a_placa()` | *top_level* | `Leitura / Consulta` | Verifica se o BGE vai carregar na CUDA neste processo. |

#### Módulo: `graph/_minhash.py` (107 LOC)
**Responsabilidade**: Implementação de MinHash e LSH para busca aproximada de conjuntos de dados.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__init__()` | `MinHash` | `Orquestração / Lifecycle` | Inicializa uma instância de MinHash. |
| `update()` | `MinHash` | `Mutação / Escrita` | Atualiza a instância de MinHash com novos dados. |
| `__init__()` | `MinHashLSH` | `Orquestração / Lifecycle` | Inicializa uma instância de MinHashLSH. |
| `insert()` | `MinHashLSH` | `Mutação / Escrita` | Insere um novo item no índice LSH. |
| `query()` | `MinHashLSH` | `Leitura / Consulta` | Consulta o índice LSH para encontrar itens similares. |
| `_lsh_integrate()` | *top_level* | `Cálculo / Algoritmo` | Realiza integração numérica para otimização de parâmetros LSH. |
| `_mh_coeffs()` | *top_level* | `Cálculo / Algoritmo` | Calcula os coeficientes para MinHash. |
| `_optimal_lsh_params()` | *top_level* | `Cálculo / Algoritmo` | Determina os parâmetros ótimos de LSH para minimizar erros. |

#### Módulo: `indice_sqlite.py` (810 LOC)
**Responsabilidade**: Implementa um índice vetorial em SQLite com busca exata em numpy, suportando operações de CRUD e busca híbrida.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__init__()` | `ClienteSqlite` | `Orquestração / Lifecycle` | Inicializa a instância de ClienteSqlite. |
| `_colecao()` | `ClienteSqlite` | `Leitura / Consulta` | Obtém a coleção. |
| `_conexao()` | `ClienteSqlite` | `Orquestração / Lifecycle` | Estabelece uma conexão com o banco de dados. |
| `backup()` | `ClienteSqlite` | `Orquestração / Lifecycle` | Realiza um backup consistente do banco de dados. |
| `close()` | `ClienteSqlite` | `Orquestração / Lifecycle` | Fecha a conexão com o banco de dados. |
| `delete_collection()` | `ClienteSqlite` | `Mutação / Escrita` | Exclui uma coleção. |
| `get_collection()` | `ClienteSqlite` | `Leitura / Consulta` | Recupera uma coleção específica. |
| `get_or_create_collection()` | `ClienteSqlite` | `Mutação / Escrita` | Recupera ou cria uma coleção. |
| `list_collections()` | `ClienteSqlite` | `Leitura / Consulta` | Lista as coleções disponíveis. |
| `verificar()` | `ClienteSqlite` | `Validação / Segurança` | Verifica a integridade do banco de dados. |
| `__init__()` | `ColecaoSqlite` | `Orquestração / Lifecycle` | Inicializa a instância de ColecaoSqlite. |
| `_carregar()` | `ColecaoSqlite` | `Leitura / Consulta` | Carrega dados da coleção. |
| `_dim()` | `ColecaoSqlite` | `Leitura / Consulta` | Obtém a dimensão da coleção. |
| `_embutir()` | `ColecaoSqlite` | `Mutação / Escrita` | Embutir dados na coleção. |
| `_filtrar()` | `ColecaoSqlite` | `Leitura / Consulta` | Filtra dados da coleção. |
| `_gravar()` | `ColecaoSqlite` | `Mutação / Escrita` | Grava dados na coleção. |
| `_linhas()` | `ColecaoSqlite` | `Leitura / Consulta` | Obtém as linhas da coleção. |
| `_mascara()` | `ColecaoSqlite` | `Validação / Segurança` | Aplica máscaras aos dados da coleção. |
| `_mascara_documento()` | `ColecaoSqlite` | `Validação / Segurança` | Aplica máscaras de documento com base em condições. |
| `_podar()` | `ColecaoSqlite` | `Mutação / Escrita` | Podar dados da coleção. |
| `_preparar()` | `ColecaoSqlite` | `Orquestração / Lifecycle` | Prepara a coleção para operações. |
| `_seq_atual()` | `ColecaoSqlite` | `Leitura / Consulta` | Obtém a sequência atual da coleção. |
| `_sincronizar()` | `ColecaoSqlite` | `Orquestração / Lifecycle` | Sincroniza a coleção com o banco de dados. |
| `add()` | `ColecaoSqlite` | `Mutação / Escrita` | Adiciona dados à coleção. |
| `buscar_texto()` | `ColecaoSqlite` | `Leitura / Consulta` | Executa uma busca textual na coleção. |
| `count()` | `ColecaoSqlite` | `Leitura / Consulta` | Contabiliza o número de itens na coleção. |
| `delete()` | `ColecaoSqlite` | `Mutação / Escrita` | Exclui dados da coleção. |
| `get()` | `ColecaoSqlite` | `Leitura / Consulta` | Recupera dados da coleção por ID. |
| `hibrida()` | `ColecaoSqlite` | `Leitura / Consulta` | Executa uma busca híbrida vetorial e textual. |
| `modify()` | `ColecaoSqlite` | `Mutação / Escrita` | Modifica dados na coleção. |
| `peek()` | `ColecaoSqlite` | `Leitura / Consulta` | Visualiza dados da coleção. |
| `query()` | `ColecaoSqlite` | `Leitura / Consulta` | Executa uma consulta na coleção. |
| `update()` | `ColecaoSqlite` | `Mutação / Escrita` | Atualiza dados na coleção. |
| `upsert()` | `ColecaoSqlite` | `Mutação / Escrita` | Atualiza ou insere dados na coleção. |
| `__init__()` | `_Cache` | `Orquestração / Lifecycle` | Inicializa a instância de Cache. |
| `_crescer()` | `_Cache` | `Mutação / Escrita` | Aumenta o tamanho da cache. |
| `_normalizar()` | `_Cache` | `Cálculo / Algoritmo` | Normaliza os dados na cache. |
| `compactar_se_preciso()` | `_Cache` | `Orquestração / Lifecycle` | Compacta a cache se necessário. |
| `por()` | `_Cache` | `Leitura / Consulta` | Recupera dados da cache por ID. |
| `tirar()` | `_Cache` | `Mutação / Escrita` | Remove dados da cache. |
| `_conectar()` | *top_level* | `Orquestração / Lifecycle` | Estabelece uma conexão com o banco de dados. |
| `_igual()` | *top_level* | `Validação / Segurança` | Compara dois valores com base nos tipos do Chroma. |
| `_numero()` | *top_level* | `Parser / AST / Extração` | Converte um valor para número. |
| `_ordem()` | *top_level* | `Parser / AST / Extração` | Determina a ordem de dois valores. |
| `_predicado()` | *top_level* | `Parser / AST / Extração` | Compila uma condição `where` do Chroma em uma função. |

#### Módulo: `migracao_indice.py` (428 LOC)
**Responsabilidade**: Módulo para migrar o índice do ChromaDB para o índice SQLite, preservando dados.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_confere_contra_o_exato()` | *top_level* | `Validação / Segurança` | Diz se `meu` e um top-k correto, aceitando empate. |
| `_consultar_filho()` | *top_level* | `Handler MCP / Endpoint` | Responde as consultas de `entrada` (JSON {colecao: matriz.npy}) no Chroma. |
| `_notas_exatas()` | *top_level* | `Cálculo / Algoritmo` | Cosseno de `q` contra TODAS as linhas, em float64, sem carregar a matriz inteira. |
| `_pasta_de_estado()` | *top_level* | `Utilitário / Helper` | Retorna `~/.delegation_core`, lido de `config` na hora da chamada para que a suite. |
| `_principal_do_filho()` | *top_level* | `Utilitário / Helper` | Função principal do filho. |
| `comparar()` | *top_level* | `Leitura / Consulta` | Roda as mesmas consultas no Chroma e no SQLite e diz onde divergem. |
| `exportar_chroma()` | *top_level* | `Leitura / Consulta` | Lê todas as coleções do Chroma e grava o formato neutro em `destino`. |
| `exportar_em_filho()` | *top_level* | `Orquestração / Lifecycle` | Exporta num processo filho. Levanta RuntimeError com o motivo se falhar. |
| `importar()` | *top_level* | `Mutação / Escrita` | Função de importação. |
| `migrar()` | *top_level* | `Orquestração / Lifecycle` | Chroma -> SQLite. Devolve o relatório; levanta RuntimeError se não puder seguir. |
| `verificar()` | *top_level* | `Validação / Segurança` | Compara o índice SQLite com a exportação. `ok` só é True se TUDO bate. |

### Domínio: `MCP Protocol & Server`
> **Módulos**: 5 | **Funções**: 100 | **LOC**: 2,687

#### Módulo: `client_tracking.py` (226 LOC)
**Responsabilidade**: Módulo responsável por rastrear quais clientes MCP estão conectados.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_safe_key()` | *top_level* | `Utilitário / Helper` | Função auxiliar para chaves seguras. |
| `_session_path()` | *top_level* | `Utilitário / Helper` | Função auxiliar para caminhos de sessão. |
| `cleanup_own_session_file()` | *top_level* | `Orquestração / Lifecycle` | Remove os arquivos de heartbeat que este processo possui. |
| `current_client_name()` | *top_level* | `Leitura / Consulta` | Nome do cliente cuja chamada está sendo tratada, dentro de uma ferramenta. |
| `list_connected_clients()` | *top_level* | `Leitura / Consulta` | Lista todos os arquivos de heartbeat de sessão, removendo os obsoletos e excluindo arquivos. |

#### Módulo: `graph/mcp_ingest.py` (386 LOC)
**Responsabilidade**: Módulo responsável pela extração de arquivos de configuração do servidor MCP.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_add_edge()` | *top_level* | `Mutação / Escrita` | Adiciona uma aresta se (source, target, relation) não estiver presente. |
| `_add_node()` | *top_level* | `Mutação / Escrita` | Adiciona um nó se ainda não estiver presente. ``kind`` é metadados, não file_type. |
| `_detect_package_from_args()` | *top_level* | `Parser / AST / Extração` | Retorna o primeiro arg que parece ser um ID de pacote npm ou pypi, caso contrário, None. |
| `_emit_server()` | *top_level* | `Utilitário / Helper` | Emite nós/arestas para uma entrada sob ``mcpServers``. |
| `_make_id()` | *top_level* | `Parser / AST / Extração` | Constrói um ID de nó estável via a receita única compartilhada (#1378). |
| `_strip_version()` | *top_level* | `Parser / AST / Extração` | Remove o suporte ``@version`` de um ID de pacote npm, preservando o escopo. |
| `extract_mcp_config()` | *top_level* | `Parser / AST / Extração` | Parseia um arquivo de configuração MCP em nós e arestas do Graphify. |
| `is_mcp_config_path()` | *top_level* | `Validação / Segurança` | Retorna True quando ``path`` é um nome de arquivo de configuração MCP reconhecido. |

#### Módulo: `server.py` (1738 LOC)
**Responsabilidade**: server.py: FastMCP tool definitions for delegation-core.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_arm_watchdog()` | *top_level* | `Utility` | Arms or re-arms the exit timer, returns False if turned off or unavailable. |
| `_bg_maintenance_wrapper()` | *top_level* | `Background Task` | Run a full maintenance cycle in the background with a fresh DelegationEngine. |
| `_confidence()` | *top_level* | `Utility` | Evaluates the confidence level of a similarity score against a model's calibration. |
| `_default_scope()` | *top_level* | `Utility` | Provides the default search scope when none is specified. |
| `_dispositivos()` | *top_level* | `Configuration` | Lists where each model is configured to run. |
| `_estado_job()` | *top_level* | `Job Management` | Check the status of a job, ensuring exclusive execution with other family jobs. |
| `_full_maintenance_cycle()` | *top_level* | `Maintenance` | Processes the inbox and performs a heal pass, used by sync and background maintenance tools. |
| `_lifespan()` | *top_level* | `Utility` | Provides the lifespan of the system or process. |
| `_page_report()` | *top_level* | `Data Processing` | Extracts one page from a report, excluding error results. |
| `_post_write_links()` | *top_level* | `Utility` | Binds notewriter.post_write_links to the module's vault. |
| `_rearm_watchdog_forever()` | *top_level* | `Utility` | Continuously re-arms the watchdog timer. |
| `_retomar_reconstrucao_na_partida()` | *top_level* | `Utility` | Waits for the index to open and executes any pending reconstruction requests. |
| `_run_or_queue()` | *top_level* | `Execution` | Runs local-model work inline or queues it if the system is busy. |
| `_serialized()` | *top_level* | `Utility` | Serializes data or objects. |
| `_vault_subfolder_error()` | *top_level* | `Validation` | Rejects folder arguments that escape the vault, returns None if safe. |
| `capabilities()` | *top_level* | `System Information` | Check the server's capabilities upon connection. |
| `compress()` | *top_level* | `Data Compression` | Compresses content when a document, email, or content over 500 words is pasted. |
| `export_session()` | *top_level* | `Session Management` | Saves a curated summary of the conversation to the vault's sessions folder. |
| `extract_source_maps()` | *top_level* | `Graph Management` | Reconstruct original sources from .js.map sidecars and graph them. |
| `graph_affected()` | *top_level* | `Analysis` | Determines what else is affected by a given query (file path or symbol). |
| `graph_build()` | *top_level* | `Graph Management` | Build a code knowledge graph for a local directory: detect and extract AST. |
| `graph_build_bg()` | *top_level* | `Background Task` | Build a code knowledge graph in the background and return a job_id immediately. |
| `graph_export()` | *top_level* | `Graph Management` | Re-export an already-built code knowledge graph into another format. |
| `graph_hook_install()` | *top_level* | `Configuration` | Installs a git post-commit hook to rebuild the code graph automatically. |
| `graph_hook_status()` | *top_level* | `Status Check` | Checks if the auto-rebuild post-commit hook is installed for the repository. |
| `graph_hook_uninstall()` | *top_level* | `Configuration` | Removes the auto-rebuild post-commit hook installed by graph_hook_install. |
| `graph_list()` | *top_level* | `Graph Management` | List previously built code graphs with details. |
| `graph_preview()` | *top_level* | `Graph Management` | Prepare for building a code knowledge graph on an unfamiliar directory. |
| `graph_report()` | *top_level* | `Data Retrieval` | Retrieves the GRAPH_REPORT.md for a previously built graph by name. |
| `heartbeat()` | *top_level* | `Health Check` | Checks the health of the system at the start of every session. |
| `ingest_configured()` | *top_level* | `Data Ingestion` | Ingest a configured source by name or all enabled sources if name is empty. |
| `ingest_configured_bg()` | *top_level* | `Background Task` | Start configured ingestion in the background and return a job_id immediately. |
| `ingest_folder()` | *top_level* | `Data Ingestion` | Index all supported files from an external folder into the vault search. |
| `ingest_folder_bg()` | *top_level* | `Background Task` | Index files from an external folder in the background and return a job_id immediately. |
| `ingest_forget()` | *top_level* | `Data Ingestion` | Drop everything previously indexed from an external path. |
| `ingest_status()` | *top_level* | `Data Ingestion` | Return the ingestion registry showing indexed external paths and timestamps. |
| `list_mcp_clients()` | *top_level* | `Client Management` | Lists MCP client surfaces currently connected to the delegation-core daemon. |
| `local_task_cancel()` | *top_level* | `Task Management` | Cancels a local-model task that has not started yet. |
| `local_task_list()` | *top_level* | `Task Management` | Lists local-model tasks, newest first, along with the submitter. |
| `local_task_status()` | *top_level* | `Task Management` | Checks the status of a queued local-model task, including its state and result. |
| `local_task_submit()` | *top_level* | `Task Management` | Queues work for the LOCAL model and returns immediately with a task ID. |
| `process_create()` | *top_level* | `Process Management` | Tracks a new process that persists across sessions and server restarts. |
| `process_get()` | *top_level* | `Process Management` | Retrieves detailed information about a tracked process. |
| `process_list()` | *top_level* | `Process Management` | Lists tracked processes with various status filters. |
| `process_update()` | *top_level* | `Process Management` | Updates a tracked process with optional parameters. |
| `read_note()` | *top_level* | `Data Retrieval` | Reads the full content of a specific vault note by filename stem. |
| `relink_folder()` | *top_level* | `Vault Management` | Adds wikilinks under `## Related` for notes in a vault subfolder. |
| `relink_folder_bg()` | *top_level* | `Background Task` | Cross-link a vault subfolder in the background and return a job_id immediately. |
| `run_maintenance()` | *top_level* | `Maintenance` | Runs vault maintenance synchronously, including classifying inbox notes and merging duplicates. |
| `run_maintenance_bg()` | *top_level* | `Background Task` | Start vault maintenance (inbox + heal pass) in the background and return a job_id immediately. |
| `run_server()` | *top_level* | `Server Operation` | Starts the server. |
| `search_vault()` | *top_level* | `Search` | Initializes a search in the vault before answering any question. |
| `search_web()` | *top_level* | `Search` | Search the web via DuckDuckGo locally and return a summary. |
| `task_status()` | *top_level* | `Job Management` | Check the status of a background job. |
| `vault_find_notes()` | *top_level* | `Vault Management` | Finds notes by literal title or path match without using embeddings or thresholds. |
| `vault_find_similar()` | *top_level* | `Vault Management` | Finds notes semantically similar to a given note, useful for merging. |
| `vault_health_detail()` | *top_level* | `Health Check` | Provides detailed health findings of the vault. |
| `vault_inbox_status()` | *top_level* | `Vault Management` | Checks files waiting in the _inbox folder before running maintenance. |
| `vault_list_notes()` | *top_level* | `Vault Management` | Lists notes in a vault folder, sorted newest first, with details like title, date, path, and size. |
| `vault_note_links()` | *top_level* | `Vault Management` | Retrieves inbound and outbound wikilinks for a specific note by vault-relative path. |
| `vault_reindex_bg()` | *top_level* | `Background Task` | Rebuild the search index in the background and return a job_id immediately. |
| `vault_rename_note()` | *top_level* | `Vault Management` | Renames a note and updates all [[wikilink]] references to it. |
| `vault_stats()` | *top_level* | `Statistics` | Returns note counts per folder, search index size, and embedding model info. |
| `vault_update_note()` | *top_level* | `Vault Management` | Appends content to an existing note and re-indexes it. |
| `window_close()` | *top_level* | `Server Management` | Unmounts an MCP server from the client configuration, freeing the context it uses. |
| `window_list()` | *top_level* | `Listing` | Lists MCP servers registered as windows that are currently mounted. |
| `window_open()` | *top_level* | `Server Management` | Mounts a registered MCP server into the client configuration. |
| `workspace_apply()` | *top_level* | `Workspace Management` | Makes the client's mounted servers match a named workspace. |
| `workspace_list()` | *top_level* | `Workspace Management` | Lists saved workspaces and identifies the active one. |
| `workspace_save()` | *top_level* | `Workspace Management` | Saves the currently mounted set of servers as a named workspace. |
| `write_note()` | *top_level* | `Data Persistence` | Writes information to the vault and indexes it immediately with BGE embeddings. |

#### Módulo: `stdio_bridge.py` (108 LOC)
**Responsabilidade**: Módulo que implementa um servidor MCP que encaminha para o daemon HTTP.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `build_proxy()` | *top_level* | `Handler MCP / Endpoint` | Cria um proxy FastMCP cujo backend é o daemon desta máquina. |
| `run()` | *top_level* | `Handler MCP / Endpoint` | Serve MCP por stdio, encaminhando tudo para o daemon. |

#### Módulo: `windows.py` (229 LOC)
**Responsabilidade**: Módulo responsável pelo gerenciamento de janelas e espaços de trabalho MCP.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_atomic_write()` | *top_level* | `Mutação / Escrita` | Escreve via um arquivo temporário e renomeia para garantir atomicidade. |
| `_empty_registry()` | *top_level* | `Mutação / Escrita` | Limpa o registro de janelas. |
| `_mounted()` | *top_level* | `Leitura / Consulta` | Verifica se um servidor está montado. |
| `apply_workspace()` | *top_level* | `Mutação / Escrita` | Faz o conjunto de nível superior montado no cliente corresponder a um espaço de trabalho nomeado. |
| `close_window()` | *top_level* | `Mutação / Escrita` | Desmonta um servidor, mantendo sua definição no registro para que possa retornar. |
| `list_windows()` | *top_level* | `Leitura / Consulta` | Lista servidores registrados que estão atualmente montados e o espaço de trabalho ativo. |
| `list_workspaces()` | *top_level* | `Leitura / Consulta` | Lista os espaços de trabalho registrados. |
| `load_registry()` | *top_level* | `Leitura / Consulta` | Carrega o catálogo de servidores e espaços de trabalho conhecidos. |
| `open_window()` | *top_level* | `Mutação / Escrita` | Monta um servidor registrado na configuração do cliente. |
| `read_client_config()` | *top_level* | `Leitura / Consulta` | Lê a configuração do cliente. |
| `save_registry()` | *top_level* | `Mutação / Escrita` | Salva o registro de janelas. |
| `save_workspace()` | *top_level* | `Mutação / Escrita` | Salva o conjunto atualmente montado sob um nome. |
| `sync_registry_from_client()` | *top_level* | `Mutação / Escrita` | Cataloga o que o cliente atualmente tem montado. |
| `write_client_config()` | *top_level* | `Mutação / Escrita` | Persiste a configuração do cliente, mantendo um backup único na primeira vez. |

### Domínio: `Queue & Background Tasks`
> **Módulos**: 5 | **Funções**: 38 | **LOC**: 1,225

#### Módulo: `gpu.py` (218 LOC)
**Responsabilidade**: Gerencia o acesso exclusivo ao GPU para BGE-m3 e llama.cpp.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `embeddings_resident()` | *top_level* | `Leitura / Consulta` | Verifica se um SentenceTransformer está armazenado em um dispositivo CUDA. |
| `held_by()` | *top_level* | `Orquestração / Lifecycle` | Toma a GPU como um gerenciador de contexto. |
| `holder()` | *top_level* | `Leitura / Consulta` | Retorna o residente que o arbitro deu a última vez a GPU. |
| `register_embeddings_owner()` | *top_level* | `Orquestração / Lifecycle` | Registra um objeto que possui uma função de embedding BGE (um VaultIndex). |
| `register_llama_owner()` | *top_level* | `Orquestração / Lifecycle` | Registra um objeto que possui um processo llama.cpp (um DelegationEngine). |
| `release_embeddings()` | *top_level* | `Mutação / Escrita` | Evicta BGE da GPU. |
| `release_llama()` | *top_level* | `Mutação / Escrita` | Para todos os processos llama.cpp registrados. |
| `take()` | *top_level* | `Orquestração / Lifecycle` | Toma a GPU para 'who' ("llama" ou "embeddings"), evictando o outro. |
| `vram_free_mib()` | *top_level* | `Leitura / Consulta` | Retorna a quantidade livre de VRAM em MiB. |

#### Módulo: `index_lock.py` (202 LOC)
**Responsabilidade**: Módulo que gerencia locks para evitar conflitos ao reabrir o índice durante consultas.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `abrir_cliente()` | *top_level* | `Orquestração / Lifecycle` | Abre o cliente do índice configurado, seja SQLite ou ChromaDB. |
| `close_chroma_client()` | *top_level* | `Orquestração / Lifecycle` | Fecha o cliente ChromaDB para iniciar uma nova sessão. |
| `index_lock_of()` | *top_level* | `Orquestração / Lifecycle` | Retorna o lock do gerenciador de índice, criado na primeira utilização. |
| `reads_index()` | *top_level* | `Orquestração / Lifecycle` | Executa um método do VaultManager com o índice mantido em modo compartilhado, sem inicialização própria. |
| `uses_index()` | *top_level* | `Orquestração / Lifecycle` | Executa um método do VaultManager com o índice mantido em modo compartilhado. |

#### Módulo: `jobs.py` (349 LOC)
**Responsabilidade**: Responsável pelo armazenamento de trabalhos em segundo plano no processo.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_chave_args()` | *top_level* | `Parser / AST / Extração` | Gera uma chave para os argumentos de uma tarefa. |
| `_familia()` | *top_level* | `Parser / AST / Extração` | Determina se duas tarefas são da mesma família. |
| `_load_durations()` | *top_level* | `Leitura / Consulta` | Carrega as durações dos trabalhos. |
| `_record_duration()` | *top_level* | `Mutação / Escrita` | Grava a duração de um trabalho. |
| `duration_hint()` | *top_level* | `Leitura / Consulta` | O que o histórico desta tarefa pode dizer honestamente sobre quanto tempo levará. |
| `em_andamento()` | *top_level* | `Leitura / Consulta` | ID de um trabalho da mesma família ainda em execução ou na fila. |
| `get()` | *top_level* | `Leitura / Consulta` | Retorna um instantâneo de um dicionário de trabalho ou None se não for encontrado. |
| `next_check_seconds()` | *top_level* | `Leitura / Consulta` | Quanto tempo esperar antes de sondar este trabalho novamente. |
| `running_count()` | *top_level* | `Leitura / Consulta` | Retorna o número de trabalhos de fundo em execução atualmente. |
| `submit()` | *top_level* | `Orquestração / Lifecycle` | Executa fn(*args, **kwargs) em um thread daemon e retorna um job_id imediatamente. |
| `typical_seconds()` | *top_level* | `Leitura / Consulta` | Tempo médio de execução dos últimos trabalhos completos desta tarefa. |

#### Módulo: `localqueue.py` (293 LOC)
**Responsabilidade**: Módulo responsável pela gestão da fila de tarefas locais.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_assinatura()` | *top_level* | `Utilitário / Helper` | Função não documentada. |
| `_now()` | *top_level* | `Utilitário / Helper` | Retorna o tempo atual. |
| `_prune()` | *top_level* | `Mutação / Escrita` | Função não documentada. |
| `_read()` | *top_level* | `Leitura / Consulta` | Lê tarefas do disco, como cópias, sem afetar o cache. |
| `_write()` | *top_level* | `Mutação / Escrita` | Função não documentada. |
| `cancel()` | *top_level* | `Mutação / Escrita` | Cancela uma tarefa que não começou, deixando uma em execução. |
| `claim_next()` | *top_level* | `Orquestração / Lifecycle` | Pega a tarefa mais antiga executável e marca-a como em execução, atomicamente. |
| `finish()` | *top_level* | `Mutação / Escrita` | Move uma tarefa para um estado terminal. |
| `get()` | *top_level* | `Leitura / Consulta` | Função não documentada. |
| `list_tasks()` | *top_level* | `Leitura / Consulta` | Lista tarefas mais recentes, filtrando por status. |
| `requeue_orphans()` | *top_level* | `Mutação / Escrita` | Retorna tarefas deixadas `running` por um daemon morto para a fila. |
| `stats()` | *top_level* | `Utilitário / Helper` | Função não documentada. |
| `submit()` | *top_level* | `Mutação / Escrita` | Coloca uma tarefa na fila e retorna o registro armazenado, incluindo seu ID. |

#### Módulo: `localworker.py` (163 LOC)
**Responsabilidade**: Módulo responsável pelo consumidor único da fila de tarefas locais.

*Módulo de constantes, tipos ou declarações puras sem funções executáveis.*

### Domínio: `CLI & Management`
> **Módulos**: 4 | **Funções**: 151 | **LOC**: 5,291

#### Módulo: `cli.py` (2339 LOC)
**Responsabilidade**: Módulo responsável pela interface de linha de comando (CLI) do delegation-core, incluindo comandos de setup, administração e gerenciamento de processos.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_add_local_flag()` | *top_level* | `Orquestração / Lifecycle` | Opta por não rotear para o daemon para comandos que escrevem no índice. |
| `_delegate()` | *top_level* | `Orquestração / Lifecycle` | Encaminha o trabalho de índice para o daemon em execução; None significa "faça você mesmo". |
| `_graph_config()` | *top_level* | `Orquestração / Lifecycle` | Configuração do grafo. |
| `_index_row_counts()` | *top_level* | `Leitura / Consulta` | Linhas por coleção, e onde a resposta veio de. |
| `_inject_related_links()` | *top_level* | `Mutação / Escrita` | Injeta links relacionados após uma escrita direta via CLI, espelhando. |
| `_process_tracker()` | *top_level* | `Orquestração / Lifecycle` | Rastreia processos. |
| `_read_content()` | *top_level* | `Leitura / Consulta` | Lê texto de um arquivo fornecido, da entrada padrão ou retorna um erro se nenhum for fornecido. |
| `_reindex_everything()` | *top_level* | `Mutação / Escrita` | Reconstrói o índice do vault E replaya toda a pasta externa ingestida. |
| `_source_row_count()` | *top_level* | `Leitura / Consulta` | Quantas linhas essa fonte de ingestão ainda tem na coleção. |
| `_texto_dos_empates()` | *top_level* | `Cálculo / Algoritmo` | Explica por que "iguais" inclui consultas cujo conjunto de ids difere. |
| `cmd_clients()` | *top_level* | `Handler MCP / Endpoint` | Aponta os clientes MCP para o daemon HTTP. |
| `cmd_compress()` | *top_level* | `Mutação / Escrita` | Comprime dados. |
| `cmd_dashboard_api()` | *top_level* | `Handler MCP / Endpoint` | API do painel de controle. |
| `cmd_doctor()` | *top_level* | `Validação / Segurança` | Diagnóstico do sistema. |
| `cmd_embed_llama()` | *top_level* | `Orquestração / Lifecycle` | Mostra ou configura o backend llama.cpp para os embeddings BGE. |
| `cmd_embed_model()` | *top_level* | `Orquestração / Lifecycle` | Lista os modelos de embedding calibrados ou muda para um. |
| `cmd_eval_search()` | *top_level* | `Cálculo / Algoritmo` | Avalia a busca com perguntas de resposta conhecida, por escopo. |
| `cmd_graph_affected()` | *top_level* | `Leitura / Consulta` | Lista os afetados pelo grafo. |
| `cmd_graph_build()` | *top_level* | `Mutação / Escrita` | Constrói o grafo. |
| `cmd_graph_extract_sources()` | *top_level* | `Leitura / Consulta` | Extrai fontes do grafo. |
| `cmd_graph_hook_install()` | *top_level* | `Orquestração / Lifecycle` | Instala um hook de grafo. |
| `cmd_graph_hook_status()` | *top_level* | `Leitura / Consulta` | Verifica o status de um hook de grafo. |
| `cmd_graph_hook_uninstall()` | *top_level* | `Orquestração / Lifecycle` | Desinstala um hook de grafo. |
| `cmd_graph_list()` | *top_level* | `Leitura / Consulta` | Lista o grafo. |
| `cmd_graph_preview()` | *top_level* | `Leitura / Consulta` | Prevê o grafo. |
| `cmd_graph_report()` | *top_level* | `Leitura / Consulta` | Relatório do grafo. |
| `cmd_index_compare()` | *top_level* | `Leitura / Consulta` | Executa as mesmas consultas nos dois índices e mostra onde divergem. |
| `cmd_index_migrate()` | *top_level* | `Mutação / Escrita` | Migra do Chroma para SQLite, com exportação neutra e verificação antes de trocar. |
| `cmd_ingest()` | *top_level* | `Mutação / Escrita` | Ingestão de dados. |
| `cmd_ingest_registry()` | *top_level* | `Mutação / Escrita` | Reconstrói `ingested_sources.json` a partir das linhas do índice. |
| `cmd_maintain()` | *top_level* | `Orquestração / Lifecycle` | Manutenção do sistema. |
| `cmd_mcp_stdio()` | *top_level* | `Handler MCP / Endpoint` | Serve MCP no stdio, encaminhando para o daemon (para Claude Desktop). |
| `cmd_note_find_similar()` | *top_level* | `Leitura / Consulta` | Encontra notas similares. |
| `cmd_note_list()` | *top_level* | `Leitura / Consulta` | Lista notas. |
| `cmd_note_read()` | *top_level* | `Leitura / Consulta` | Lê uma nota. |
| `cmd_note_update()` | *top_level* | `Mutação / Escrita` | Atualiza uma nota. |
| `cmd_note_write()` | *top_level* | `Mutação / Escrita` | Escreve uma nota, através do daemon quando um está em execução. |
| `cmd_ocr_setup()` | *top_level* | `Orquestração / Lifecycle` | Baixa os dados de idioma do tesseract (versão "fast") para ~/.delegation_core/tessdata. |
| `cmd_post_install()` | *top_level* | `Orquestração / Lifecycle` | Finaliza uma instalação: documentação, hooks, habilidades, painel, serviço, clientes. |
| `cmd_process_create()` | *top_level* | `Orquestração / Lifecycle` | Cria um processo. |
| `cmd_process_get()` | *top_level* | `Leitura / Consulta` | Obtém um processo. |
| `cmd_process_list()` | *top_level* | `Leitura / Consulta` | Lista processos. |
| `cmd_process_update()` | *top_level* | `Mutação / Escrita` | Atualiza um processo. |
| `cmd_recover_index()` | *top_level* | `Mutação / Escrita` | Move o índice de lado e deixa o daemon reconstruí-lo na próxima partida. |
| `cmd_reindex()` | *top_level* | `Mutação / Escrita` | Reindexa o sistema. |
| `cmd_relink()` | *top_level* | `Mutação / Escrita` | Relinka dados. |
| `cmd_repair_empty_source()` | *top_level* | `Mutação / Escrita` | Encontra e conserta notas sintetizadas a partir de arquivos sem texto. |
| `cmd_run()` | *top_level* | `Orquestração / Lifecycle` | Executa um comando. |
| `cmd_search()` | *top_level* | `Leitura / Consulta` | Executa uma busca. |
| `cmd_service()` | *top_level* | `Orquestração / Lifecycle` | Gerencia o registro de serviço per-usuário do daemon. |
| `cmd_session()` | *top_level* | `Orquestração / Lifecycle` | Gerencia a política de captura para transcrições de sessões de Claude Code e Codex. |
| `cmd_setup()` | *top_level* | `Orquestração / Lifecycle` | Configuração inicial do sistema. |
| `cmd_status()` | *top_level* | `Leitura / Consulta` | Verifica o status do sistema. |
| `cmd_uninstall()` | *top_level* | `Orquestração / Lifecycle` | Remove a instalação, mantendo o vault e os modelos baixados. |
| `cmd_update()` | *top_level* | `Orquestração / Lifecycle` | Atualiza o pacote instalado para a versão mais recente. |
| `cmd_update_finish()` | *top_level* | `Orquestração / Lifecycle` | Segunda metade do `update`, executada pelo mesmo no versão do pip recém-instalada. |
| `main()` | *top_level* | `Orquestração / Lifecycle` | Ponto de entrada principal do programa. |

#### Módulo: `doctor.py` (770 LOC)
**Responsabilidade**: Módulo responsável por verificações de integridade e diagnósticos do sistema.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_caminho_do_cli()` | *top_level* | `Utilitário / Helper` | Obtém o caminho do cli.py. |
| `_check_indice_sqlite()` | *top_level* | `Validação / Segurança` | Verifica a integridade do índice SQLite. |
| `_descreve_abandonadas()` | *top_level* | `Utilitário / Helper` | Gera um aviso e descrição para pastas abandonadas. |
| `_e_backup_de_indice()` | *top_level* | `Utilitário / Helper` | Verifica se há um backup do índice. |
| `_pastas_de_indice_abandonadas()` | *top_level* | `Leitura / Consulta` | Lista pastas de índice abandonadas. |
| `_tamanho_mb()` | *top_level* | `Utilitário / Helper` | Calcula o tamanho em MB. |
| `aviso_de_escala_do_indice()` | *top_level* | `Utilitário / Helper` | Gera um aviso se o índice for grande demais para a busca exata. |
| `check_devices()` | *top_level* | `Validação / Segurança` | Verifica onde cada modelo roda e se há conflitos de dispositivo. |
| `check_embed_backend()` | *top_level* | `Validação / Segurança` | Verifica onde o BGE roda e se o Mac Apple Silicon está configurado corretamente. |
| `check_engine_mode()` | *top_level* | `Utilitário / Helper` | Verifica o modo do motor. |
| `check_fts_integrity()` | *top_level* | `Validação / Segurança` | Verifica se a tabela de pesquisa FTS5 do SQLite está saudável ou corrompida. |
| `check_graph_extra()` | *top_level* | `Utilitário / Helper` | Verifica a integridade do gráfico extra. |
| `check_graph_registry()` | *top_level* | `Utilitário / Helper` | Verifica o registro do gráfico. |
| `check_hooks()` | *top_level* | `Validação / Segurança` | Verifica se os hooks de sessão estão registrados corretamente. |
| `check_index_integrity()` | *top_level* | `Validação / Segurança` | Verifica a integridade do índice perguntando diretamente ao índice. |
| `check_index_location()` | *top_level* | `Validação / Segurança` | Verifica se o índice está em uma pasta sincronizada com a nuvem. |
| `check_index_writers()` | *top_level* | `Validação / Segurança` | Verifica se todos os comandos de CLI que abrem o índice passam pelo daemon. |
| `check_ingest_registry()` | *top_level* | `Utilitário / Helper` | Verifica o registro de ingestão. |
| `check_local_fallback()` | *top_level* | `Validação / Segurança` | Verifica a configuração de fallback local. |
| `check_orphan_segments()` | *top_level* | `Validação / Segurança` | Detecta segmentos órfãos deixados por trás no disco. |
| `check_vault_folders()` | *top_level* | `Validação / Segurança` | Verifica se as pastas configuradas existem e não há conflitos de nomes. |
| `clean_orphan_segments()` | *top_level* | `Mutação / Escrita` | Remove segmentos órfãos não referenciados no SQLite. |
| `rebuild_fts()` | *top_level* | `Mutação / Escrita` | Reconstrói o índice FTS5 do SQLite a partir da tabela de documentos. |
| `run_all()` | *top_level* | `Orquestração / Lifecycle` | Executa todas as verificações e retorna o status e contagens. |
| `sondar_indice()` | *top_level* | `Orquestração / Lifecycle` | Executa uma sonda no processo filho. |

#### Módulo: `installer.py` (1110 LOC)
**Responsabilidade**: Módulo responsável por instalar, atualizar e desinstalar o pacote delegation-core, incluindo a gestão de configurações e integrações.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_dashboard_artifact()` | *top_level* | `Leitura / Consulta` | Função não documentada relacionada ao dashboard. |
| `_desktop_entry_text()` | *top_level* | `Leitura / Consulta` | Função não documentada relacionada à entrada de desktop. |
| `_dist_info()` | *top_level* | `Leitura / Consulta` | Retorna o diretório .dist-info do pacote instalado, ou None. |
| `_download_release_asset()` | *top_level* | `Leitura / Consulta` | Baixa um ativo do último GitHub release via `gh`, ou None. |
| `_finish_in_new_code()` | *top_level* | `Mutação / Escrita` | Executa `finish_update` em um novo interpretador, ou seja, na nova versão. |
| `_git()` | *top_level* | `Leitura / Consulta` | Função não documentada relacionada ao Git. |
| `_install_appimage()` | *top_level* | `Mutação / Escrita` | Coloca o AppImage e dá a ele uma entrada de menu real com um ícone real. |
| `_pip_install()` | *top_level* | `Mutação / Escrita` | Reinstala o pacote da origem com extras opcionais se construídos. |
| `_running_from()` | *top_level* | `Leitura / Consulta` | Verifica se o interpretador está executando este código instalado sob `directory`. |
| `config_is_unreadable()` | *top_level* | `Leitura / Consulta` | Verifica se config.json está presente e não pode ser analisado. |
| `configured_vault_path()` | *top_level* | `Leitura / Consulta` | Retorna o caminho do vault registrado em config.json, ou "" se não legível. |
| `finish_update()` | *top_level* | `Mutação / Escrita` | Passos de `update` que vêm após `pip install`. |
| `git_state()` | *top_level* | `Leitura / Consulta` | Retorna o estado do Git: branch, commit e distância em relação ao upstream. |
| `install_agents()` | *top_level* | `Mutação / Escrita` | Copia definições de agente em ~/.claude/agents, nunca sobrescrevendo. |
| `install_codex_skills()` | *top_level* | `Mutação / Escrita` | Copia habilidades Codex para o local de descoberta do usuário de Codex, nunca sobrescrevendo. |
| `install_dashboard()` | *top_level* | `Mutação / Escrita` | Instala o dashboard Tauri, preferindo uma build local sobre uma release. |
| `install_skills()` | *top_level* | `Mutação / Escrita` | Copia habilidades Claude em ~/.claude/skills, nunca sobrescrevendo. |
| `is_editable()` | *top_level* | `Leitura / Consulta` | Verifica se o ambiente virtual aponta para a árvore de origem em vez de copiá-la. |
| `is_git_checkout()` | *top_level* | `Leitura / Consulta` | Função não documentada relacionada ao Git. |
| `post_install()` | *top_level* | `Mutação / Escrita` | Tudo o que install.sh e install.bat fizeram após `pip install`. |
| `refresh_shipped_files()` | *top_level* | `Mutação / Escrita` | Copia arquivos AGENT_GUIDE/CLAUDE_SYSTEM_PROMPT para CONFIG_DIR. |
| `repair_client_configs()` | *top_level* | `Mutação / Escrita` | Atualiza as entradas do cliente MCP que uma atualização não deve deixar obsoletas. |
| `repo_slug()` | *top_level* | `Leitura / Consulta` | Retorna o GitHub `owner/name` para pull das releases do dashboard. |
| `source_root()` | *top_level* | `Leitura / Consulta` | Retorna o diretório de origem do pacote instalado, ou None se desconhecível. |
| `stale_dist_copies()` | *top_level* | `Leitura / Consulta` | Retorna arquivos .dist que são idênticos ao arquivo ao seu lado. |
| `uninstall()` | *top_level* | `Mutação / Escrita` | Remove a instalação do delegation-core, deixando o vault e os modelos intactos. |
| `update()` | *top_level* | `Mutação / Escrita` | Atualiza o pacote instalado para a versão mais recente da origem de forma segura. |
| `vault_is_inside_config_dir()` | *top_level* | `Leitura / Consulta` | Verifica se removendo os conteúdos de CONFIG_DIR também removeria o conteúdo do vault. |
| `venv_pending_path()` | *top_level* | `Leitura / Consulta` | Retorna onde o sentinela reside, resolvido quando solicitado e não no momento da importação. |

#### Módulo: `wizard.py` (1072 LOC)
**Responsabilidade**: Módulo responsável por um assistente interativo de configuração para o delegation-core.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_apple_silicon()` | *top_level* | `Utilitário / Helper` | Verifica se a máquina é Apple Silicon. |
| `_check_internet()` | *top_level* | `Validação / Segurança` | Verifica a conectividade à internet. |
| `_check_linux_packages()` | *top_level* | `Validação / Segurança` | Verifica pacotes do Linux necessários. |
| `_check_xcode()` | *top_level* | `Validação / Segurança` | Verifica a instalação do Xcode. |
| `_clientes_detectados()` | *top_level* | `Leitura / Consulta` | Detecta clientes MCP existentes na máquina. |
| `_completion()` | *top_level* | `Utilitário / Helper` | Finaliza o assistente. |
| `_conflicts_with_config_dir()` | *top_level* | `Validação / Segurança` | Verifica conflitos com o diretório de configuração. |
| `_find_mlx_server()` | *top_level* | `Leitura / Consulta` | Encontra o servidor MLX. |
| `_header()` | *top_level* | `Utilitário / Helper` | Exibe o cabeçalho. |
| `_hosts_inalcancaveis()` | *top_level* | `Validação / Segurança` | Verifica hosts inalcançáveis, respeitando HTTP(S)_PROXY. |
| `_install_linux_packages()` | *top_level* | `Mutação / Escrita` | Instala pacotes do Linux necessários. |
| `_install_xcode()` | *top_level* | `Mutação / Escrita` | Instala o Xcode. |
| `_menu()` | *top_level* | `Utilitário / Helper` | Exibe o menu. |
| `_menu_index()` | *top_level* | `Utilitário / Helper` | Retorna o índice base zero da escolha do menu. |
| `_pedir_binario()` | *top_level* | `Utilitário / Helper` | Pede o caminho de um executável até que ele exista ou seja deixado para depois. |
| `_pedir_modelo_mlx()` | *top_level* | `Utilitário / Helper` | Pede o modelo MLX. |
| `_setup_startup()` | *top_level* | `Mutação / Escrita` | Configura a inicialização. |
| `_startup_launchd()` | *top_level* | `Mutação / Escrita` | Configura a inicialização com launchd. |
| `_startup_systemd()` | *top_level* | `Mutação / Escrita` | Configura a inicialização com systemd. |
| `_startup_task_scheduler()` | *top_level* | `Mutação / Escrita` | Configura a inicialização com um agendador de tarefas. |
| `_step_bge()` | *top_level* | `Mutação / Escrita` | Configura o BGE. |
| `_step_binary()` | *top_level* | `Mutação / Escrita` | Configura o binário. |
| `_step_connect()` | *top_level* | `Mutação / Escrita` | Registra o daemon e conecta os clientes MCP existentes. |
| `_step_embed_llama()` | *top_level* | `Mutação / Escrita` | Configura o BGE para rodar pelo llama.cpp em Apple Silicon. |
| `_step_embedding_model()` | *top_level* | `Mutação / Escrita` | Escolhe o modelo de busca, grava a configuração e baixa o modelo. |
| `_step_engine_mode()` | *top_level* | `Mutação / Escrita` | Escolhe onde a geração de código será executada. |
| `_step_features()` | *top_level* | `Mutação / Escrita` | Pergunta sobre configurações v0.2: síntese, linguagem, modo orçamentário. |
| `_step_index()` | *top_level* | `Mutação / Escrita` | Configura o índice. |
| `_step_index_location()` | *top_level* | `Mutação / Escrita` | Configura a localização do índice dentro do Vault. |
| `_step_local_engine_kind()` | *top_level* | `Mutação / Escrita` | Configura o tipo de motor local. |
| `_step_mlx()` | *top_level* | `Mutação / Escrita` | Configura o (binário, modelo) do MLX. |
| `_step_model()` | *top_level* | `Mutação / Escrita` | Configura o modelo. |
| `_step_startup()` | *top_level* | `Mutação / Escrita` | Configura a inicialização. |
| `_step_system_check()` | *top_level* | `Validação / Segurança` | Executa verificações de sistema. |
| `_step_vault()` | *top_level* | `Mutação / Escrita` | Configura o Vault. |
| `_systemd_literal()` | *top_level* | `Utilitário / Helper` | Converte um caminho controlado pelo usuário para um arquivo de unidade systemd. |
| `_verify_python_packages()` | *top_level* | `Validação / Segurança` | Verifica pacotes Python necessários. |
| `_warn_config_dir_conflict()` | *top_level* | `Validação / Segurança` | Avisa sobre conflitos com o diretório de configuração. |
| `_welcome()` | *top_level* | `Utilitário / Helper` | Exibe a mensagem de boas-vindas. |
| `run_wizard()` | *top_level* | `Orquestração / Lifecycle` | Executa o assistente interativo de configuração. |

### Domínio: `Security & Auth`
> **Módulos**: 3 | **Funções**: 17 | **LOC**: 632

#### Módulo: `auth.py` (77 LOC)
**Responsabilidade**: Autenticação de tokens bearer para o transporte HTTP.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `__init__()` | `LocalTokenAuth` | `Orquestração / Lifecycle` | Inicializa a autenticação de token local. |
| `verify_token()` | `LocalTokenAuth` | `Validação / Segurança` | Verifica a validade do token bearer fornecido. |

#### Módulo: `graph/security.py` (460 LOC)
**Responsabilidade**: Módulo responsável por funções de segurança, validação de URLs e manipulação de conexões HTTP/HTTPS.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_build_opener()` | *top_level* | `Utilitário / Helper` | Constrói um opener para URLs. |
| `_ip_is_blocked()` | *top_level* | `Validação / Segurança` | Verifica se o IP está em um intervalo privado/reservado/interno. |
| `_max_graph_file_bytes()` | *top_level* | `Cálculo / Algoritmo` | Retorna o tamanho máximo em bytes para o arquivo graph.json. |
| `_resolve_and_validate()` | *top_level* | `Validação / Segurança` | Resolve o host uma vez e retorna o endereço IP validado. |
| `_sanitize_metadata_string()` | *top_level* | `Sanitização` | Retorna uma string livre de caracteres de controle, HTML escapada e limitada. |
| `_sanitize_metadata_value()` | *top_level* | `Sanitização` | Sanitiza um valor de metadados enquanto preserva tipos JSON compatíveis. |
| `check_graph_file_size_cap()` | *top_level* | `Validação / Segurança` | Rejeita o caminho se o tamanho exceder o limite configurado. |
| `safe_fetch()` | *top_level* | `Leitura / Consulta` | Busca a URL e retorna os bytes brutos. |
| `safe_fetch_text()` | *top_level* | `Leitura / Consulta` | Busca a URL e retorna o texto decodificado (UTF-8, substituindo bytes inválidos). |
| `sanitize_label()` | *top_level* | `Sanitização` | Remove caracteres de controle e limita o comprimento. |
| `sanitize_metadata()` | *top_level* | `Sanitização` | Sanitiza chaves e valores de metadados antes da exportação do gráfico. |
| `validate_graph_path()` | *top_level* | `Validação / Segurança` | Valida que o caminho permanece dentro do diretório base. |
| `validate_url()` | *top_level* | `Validação / Segurança` | Valida se a URL é http ou https e não aponta para um IP privado/interno. |

#### Módulo: `graph/validate.py` (95 LOC)
**Responsabilidade**: Módulo responsável por validações de extração e gráficos.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `assert_valid()` | *top_level* | `Validação / Segurança` | Lança ValueError com todos os erros se a extração for inválida. |
| `validate_extraction()` | *top_level* | `Validação / Segurança` | Valida um dicionário JSON de extração contra o esquema graphify. |

### Domínio: `Utilities & Helpers`
> **Módulos**: 2 | **Funções**: 1 | **LOC**: 92

#### Módulo: `imagens/__init__.py` (7 LOC)
**Responsabilidade**: Este módulo contém funções para converter imagens em texto buscável, incluindo extração de metadados EXIF e OCR.

*Módulo de constantes, tipos ou declarações puras sem funções executáveis.*

#### Módulo: `junk.py` (85 LOC)
**Responsabilidade**: Responsável pela detecção de arquivos de boilerplate.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `is_junk()` | *top_level* | `Validação / Segurança` | Retorna uma razão de skip se o arquivo parecer boilerplate, caso contrário, None. |

### Domínio: `Dashboard & Telemetry`
> **Módulos**: 1 | **Funções**: 42 | **LOC**: 1,127

#### Módulo: `dashboard_api.py` (1127 LOC)
**Responsabilidade**: Este módulo implementa a API HTTP local para o painel Tauri, fornecendo endpoints para várias operações relacionadas ao dashboard e ao armazenamento de dados.

| Função / Método | Escopo | Papel | Descrição |
| :--- | :--- | :--- | :--- |
| `_authorized()` | `_Handler` | `Validação / Segurança` | Verifica se a solicitação carrega o token bearer do daemon. |
| `_cors_origin()` | `_Handler` | `Utilitário / Helper` | Determina a origem a ser refletida no cabeçalho Access-Control-Allow-Origin. |
| `_drain_body()` | `_Handler` | `Utilitário / Helper` | Consumo do corpo de uma solicitação que será rejeitada. |
| `_handle_config_get()` | `_Handler` | `Leitura / Consulta` | Obtém a configuração. |
| `_handle_config_update()` | `_Handler` | `Mutação / Escrita` | Atualiza a configuração. |
| `_handle_graphs_affected()` | `_Handler` | `Leitura / Consulta` | Obtém gráficos afetados. |
| `_handle_graphs_get()` | `_Handler` | `Leitura / Consulta` | Obtém gráficos. |
| `_handle_llama_start()` | `_Handler` | `Orquestração / Lifecycle` | Inicia o servidor llama. |
| `_handle_llama_stop()` | `_Handler` | `Orquestração / Lifecycle` | Para o servidor llama. |
| `_handle_note_create()` | `_Handler` | `Mutação / Escrita` | Cria uma nota. |
| `_handle_note_rename()` | `_Handler` | `Mutação / Escrita` | Renomeia uma nota. |
| `_handle_note_save()` | `_Handler` | `Mutação / Escrita` | Salva uma nota existente. |
| `_handle_processes_create()` | `_Handler` | `Mutação / Escrita` | Cria um processo. |
| `_handle_processes_get()` | `_Handler` | `Leitura / Consulta` | Obtém detalhes de um processo. |
| `_handle_processes_list()` | `_Handler` | `Leitura / Consulta` | Lista os processos. |
| `_handle_processes_update()` | `_Handler` | `Mutação / Escrita` | Atualiza um processo. |
| `_handle_purge_orphans()` | `_Handler` | `Mutação / Escrita` | Limpa orfanatos. |
| `_handle_vault_backlinks()` | `_Handler` | `Leitura / Consulta` | Obtém backlinks de uma nota. |
| `_handle_vault_find()` | `_Handler` | `Leitura / Consulta` | Procura notas por título ou caminho. |
| `_handle_vault_note()` | `_Handler` | `Leitura / Consulta` | Obtém uma nota específica. |
| `_handle_vault_notes()` | `_Handler` | `Leitura / Consulta` | Obtém notas. |
| `_handle_vault_search()` | `_Handler` | `Leitura / Consulta` | Realiza uma pesquisa no armazenamento de notas. |
| `_handle_vault_tree()` | `_Handler` | `Leitura / Consulta` | Obtém a estrutura do armazenamento de notas. |
| `_log_disconnect()` | `_Handler` | `Utilitário / Helper` | Registra desconexões de clientes. |
| `_read_json_body()` | `_Handler` | `Parser / AST / Extração` | Parseia o corpo da solicitação como JSON. |
| `_route_get()` | `_Handler` | `Handler MCP / Endpoint` | Roteia solicitações GET. |
| `_route_post()` | `_Handler` | `Handler MCP / Endpoint` | Roteia solicitações POST. |
| `_send_error_response()` | `_Handler` | `Utilitário / Helper` | Envia uma resposta de erro 500. |
| `_send_json()` | `_Handler` | `Utilitário / Helper` | Envia uma resposta JSON. |
| `_serve()` | `_Handler` | `Orquestração / Lifecycle` | Executa o roteamento de uma solicitação sob o tratamento de erros compartilhado por todos os verbos. |
| `do_GET()` | `_Handler` | `Handler MCP / Endpoint` | Manipula solicitações GET. |
| `do_OPTIONS()` | `_Handler` | `Handler MCP / Endpoint` | Manipula solicitações OPTIONS. |
| `do_POST()` | `_Handler` | `Handler MCP / Endpoint` | Manipula solicitações POST. |
| `log_message()` | `_Handler` | `Utilitário / Helper` | Registra uma mensagem de log. |
| `_build_vault_graph()` | *top_level* | `Parser / AST / Extração` | Parseia todas as notas do armazenamento para extrair [[wikilinks]]. |
| `_config_publico()` | *top_level* | `Leitura / Consulta` | Obtém a configuração pública. |
| `_find_llama_process()` | *top_level* | `Leitura / Consulta` | Encontra o processo de servidor llama em execução. |
| `_get_engine()` | *top_level* | `Utilitário / Helper` | Constrói o DelegationEngine usado para iniciar o llama.cpp. |
| `_start_parent_watchdog()` | *top_level* | `Orquestração / Lifecycle` | Monitora o processo pai e encerra este processo se o pai morrer. |
| `_status()` | *top_level* | `Leitura / Consulta` | Verifica o status do sistema. |
| `run()` | *top_level* | `Orquestração / Lifecycle` | Executa o servidor. |
| `serve_in_process()` | *top_level* | `Handler MCP / Endpoint` | Serve as mesmas rotas dentro do daemon. |
