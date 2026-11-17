"""A static catalog of self-hosted services: name, domain, port and role of each.

It is reference data only. Until 17/11/2026 it also "routed" requests and reported the gateway
HEALTHY, without contacting any service; both were removed for v0.17.0.
"""

from typing import Dict, Any, List, Optional


class HomelabServiceGateway:
    """The catalog and lookups over it. Nothing here makes a network call."""

    CATALOG: Dict[str, Dict[str, Any]] = {
        # --- Identidade & Segurança ---
        "vaultwarden": {
            "name": "vaultwarden",
            "domain": "identity_secrets",
            "port": 8080,
            "role": "Cofre de senhas e segredos criptografados compativel com Bitwarden (Rust)",
            "upstream_repo": "dani-garcia/vaultwarden",
            "auth_required": True,
        },
        "supabase": {
            "name": "supabase",
            "domain": "backend_baas",
            "port": 8000,
            "role": "Plataforma BaaS completa: Postgres, Auth, Realtime e Edge Functions",
            "upstream_repo": "supabase/supabase",
            "auth_required": True,
        },
        "appwrite": {
            "name": "appwrite",
            "domain": "backend_baas",
            "port": 80,
            "role": "Backend-as-a-Service para desenvolvedores web, mobile e Flutter",
            "upstream_repo": "appwrite/appwrite",
            "auth_required": True,
        },
        "baserow": {
            "name": "baserow",
            "domain": "database_nocode",
            "port": 80,
            "role": "Banco de dados relacional no-code e alternativa aberta ao Airtable",
            "upstream_repo": "baserow/baserow",
            "auth_required": True,
        },
        "nocodb": {
            "name": "nocodb",
            "domain": "database_nocode",
            "port": 8080,
            "role": "Transforma bancos relacionais existentes em planilhas inteligentes",
            "upstream_repo": "nocodb/nocodb",
            "auth_required": True,
        },
        # --- Armazenamento, Arquivos & Midia ---
        "immich": {
            "name": "immich",
            "domain": "storage_media",
            "port": 2283,
            "role": "Gerenciamento e backup de fotos/videos de alta performance com IA",
            "upstream_repo": "immich-app/immich",
            "auth_required": True,
        },
        "jellyfin": {
            "name": "jellyfin",
            "domain": "storage_media",
            "port": 8096,
            "role": "Servidor de streaming de multimidia (video/musica) 100% livre",
            "upstream_repo": "jellyfin/jellyfin",
            "auth_required": True,
        },
        "paperless-ngx": {
            "name": "paperless-ngx",
            "domain": "storage_media",
            "port": 8000,
            "role": "Sistema de gestao de documentos fisicos digitalizados com OCR e tags",
            "upstream_repo": "paperless-ngx/paperless-ngx",
            "auth_required": True,
        },
        "nextcloud-server": {
            "name": "nextcloud-server",
            "domain": "storage_sync",
            "port": 80,
            "role": "Suite de nuvem pessoal para sincronizacao de arquivos, calendario e contatos",
            "upstream_repo": "nextcloud/server",
            "auth_required": True,
        },
        "syncthing": {
            "name": "syncthing",
            "domain": "storage_sync",
            "port": 8384,
            "role": "Sincronizacao continua descentralizada P2P entre dispositivos",
            "upstream_repo": "syncthing/syncthing",
            "auth_required": False,
        },
        "localsend": {
            "name": "localsend",
            "domain": "storage_sync",
            "port": 53317,
            "role": "Compartilhamento seguro de arquivos em rede local sem internet",
            "upstream_repo": "localsend/localsend",
            "auth_required": False,
        },
        # --- Produtividade, Git & Comunicacao ---
        "gitea": {
            "name": "gitea",
            "domain": "git_cicd",
            "port": 3000,
            "role": "Hospedagem Git ultraleve com CI/CD, issues e pull requests em Go",
            "upstream_repo": "go-gitea/gitea",
            "auth_required": True,
        },
        "cal.com": {
            "name": "cal.com",
            "domain": "productivity",
            "port": 3000,
            "role": "Infraestrutura de agendamento de reunioes e integracao de calendarios",
            "upstream_repo": "calcom/cal.com",
            "auth_required": True,
        },
        "formbricks": {
            "name": "formbricks",
            "domain": "operations",
            "port": 3000,
            "role": "Suite aberta de pesquisas e micro-pesquisas de feedback do usuario",
            "upstream_repo": "formbricks/formbricks",
            "auth_required": True,
        },
        "listmonk": {
            "name": "listmonk",
            "domain": "operations",
            "port": 9000,
            "role": "Gerenciador de newsletters e listas de emails de alta velocidade em Go",
            "upstream_repo": "knadh/listmonk",
            "auth_required": True,
        },
        "mealie": {
            "name": "mealie",
            "domain": "productivity",
            "port": 9000,
            "role": "Planejador de refeicoes e gerenciador de receitas culinarias",
            "upstream_repo": "mealie-recipes/mealie",
            "auth_required": True,
        },
        # --- Colaboracao & Visual ---
        "excalidraw": {
            "name": "excalidraw",
            "domain": "collaboration",
            "port": 80,
            "role": "Quadro branco colaborativo virtual com aparencia de desenho a mao",
            "upstream_repo": "excalidraw/excalidraw",
            "auth_required": False,
        },
        "penpot": {
            "name": "penpot",
            "domain": "collaboration",
            "port": 9001,
            "role": "Plataforma web de design e prototipagem vetorial para times",
            "upstream_repo": "penpot/penpot",
            "auth_required": True,
        },
        "appflowy": {
            "name": "AppFlowy",
            "domain": "collaboration",
            "port": 8000,
            "role": "Alternativa aberta ao Notion construida em Flutter e Rust",
            "upstream_repo": "AppFlowy-IO/AppFlowy",
            "auth_required": True,
        },
        # --- Inteligencia Artificial & Conhecimento ---
        "librechat": {
            "name": "LibreChat",
            "domain": "ai_chat",
            "port": 3080,
            "role": "Interface unificada multi-provedor de chat de IA compativel com OpenAI",
            "upstream_repo": "danny-avila/LibreChat",
            "auth_required": True,
        },
        "libretranslate": {
            "name": "LibreTranslate",
            "domain": "ai_translation",
            "port": 5000,
            "role": "API local de traducao de maquina automatica e privada",
            "upstream_repo": "LibreTranslate/LibreTranslate",
            "auth_required": False,
        },
        "searxng": {
            "name": "searxng",
            "domain": "knowledge",
            "port": 8080,
            "role": "Metabuscador agregador de pesquisas na web sem rastreamento",
            "upstream_repo": "searxng/searxng",
            "auth_required": False,
        },
        "freshrss": {
            "name": "FreshRSS",
            "domain": "knowledge",
            "port": 80,
            "role": "Agregador e leitor de feeds RSS/Atom auto-hospedado de alta performance",
            "upstream_repo": "FreshRSS/FreshRSS",
            "auth_required": True,
        },
        # --- Infraestrutura, Redes & Observabilidade ---
        "pi-hole": {
            "name": "pi-hole",
            "domain": "infrastructure",
            "port": 80,
            "role": "Servidor DNS local bloqueador de anuncios e rastreadores em nivel de rede",
            "upstream_repo": "pi-hole/pi-hole",
            "auth_required": True,
        },
        "uptime-kuma": {
            "name": "uptime-kuma",
            "domain": "infrastructure",
            "port": 3001,
            "role": "Painel de monitoramento de disponibilidade e pagina de status",
            "upstream_repo": "louislam/uptime-kuma",
            "auth_required": True,
        },
        "homepage": {
            "name": "homepage",
            "domain": "infrastructure",
            "port": 3000,
            "role": "Dashboard moderno e integrado de servicos locais do servidor homelab",
            "upstream_repo": "gethomepage/homepage",
            "auth_required": False,
        },
        "home-assistant-core": {
            "name": "home-assistant-core",
            "domain": "infrastructure",
            "port": 8123,
            "role": "Plataforma central de automacao residencial e controle IoT",
            "upstream_repo": "home-assistant/core",
            "auth_required": True,
        },
        "posthog": {
            "name": "posthog",
            "domain": "analytics",
            "port": 8000,
            "role": "Plataforma aberta de analise de produto, gravacoes de sessao e feature flags",
            "upstream_repo": "PostHog/posthog",
            "auth_required": True,
        },
        "superset": {
            "name": "superset",
            "domain": "analytics",
            "port": 8088,
            "role": "Exploracao de dados corporativos e construcao de dashboards SQL",
            "upstream_repo": "apache/superset",
            "auth_required": True,
        },
    }

    def __init__(self):
        pass

    def list_services(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retorna os serviços do catálogo, com filtro opcional por domínio."""
        if not domain:
            return list(self.CATALOG.values())
        return [s for s in self.CATALOG.values() if s.get("domain") == domain]

    def list_domains(self) -> List[str]:
        """Retorna os domínios funcionais únicos do homelab."""
        return sorted(list(set(s["domain"] for s in self.CATALOG.values())))

    def summary(self) -> Dict[str, Any]:
        """Size of the catalog. It is a static list: nothing here contacts the services."""
        domains = self.list_domains()
        return {"total_services": len(self.CATALOG), "domains_count": len(domains), "domains": domains}


_GLOBAL_HOMELAB_GATEWAY: Optional[HomelabServiceGateway] = None


def get_homelab_gateway() -> HomelabServiceGateway:
    global _GLOBAL_HOMELAB_GATEWAY
    if _GLOBAL_HOMELAB_GATEWAY is None:
        _GLOBAL_HOMELAB_GATEWAY = HomelabServiceGateway()
    return _GLOBAL_HOMELAB_GATEWAY
