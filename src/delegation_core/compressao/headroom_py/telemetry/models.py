"""Ligacao: so a estrutura ToolSignature que o Kompress monta (e a telemetria desligada ignora)."""

from dataclasses import dataclass


@dataclass
class ToolSignature:
    structure_hash: str
    field_count: int = 0
    has_nested_objects: bool = False
    has_arrays: bool = False
    max_depth: int = 0
    string_field_count: int = 0
    has_error_like_field: bool = False
    has_message_like_field: bool = False
