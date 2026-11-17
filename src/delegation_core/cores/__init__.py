"""
Pacote unificado de núcleos funcionais consolidando os softwares do ecossistema:
- agent_harness: Banco FTS5 de skills, sanitização anti-slop e ferramentas de inspeção
- multimodal: Ingestão multimodal (OCR, Markdown, Whisper STT, TTS, Diagramas)
- orchestration: Orquestração DAG assíncrona, fila multiagente, CI autônomo e telemetria LLM
- platform: Plataforma local com poda de contexto, guardião de concorrência/orçamento, grafo de código e telemetria
"""

from .unified_facade import UnifiedCoresBridge, get_cores_bridge

__all__ = ["UnifiedCoresBridge", "get_cores_bridge"]
