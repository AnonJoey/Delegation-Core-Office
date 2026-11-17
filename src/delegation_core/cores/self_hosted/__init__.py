"""
Módulo de Integração e Gateway Homelab Self-Hosted (Categoria 5 do ecossistema).
Consolida o catálogo, portas e roteamento unificado dos 29 serviços self-hosted.
"""

from .gateway import HomelabServiceGateway, get_homelab_gateway

__all__ = ["HomelabServiceGateway", "get_homelab_gateway"]
