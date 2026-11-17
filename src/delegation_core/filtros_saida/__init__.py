"""Filtros de saida de comando: o motor TOML do RTK, portado de Rust.

RTK (Rust Token Killer, github.com/rtk-ai/rtk, Apache 2.0) corta a saida de
comandos antes de o agente le-la. Os filtros declarativos dele ficam em TOML
(`rtk/*.toml`, copiados sem mudanca; licenca em `THIRD_PARTY_LICENSES/RTK-LICENSE-Apache-2.0`) e o
motor que os aplica, `src/core/toml_filter.rs`, esta portado em `motor.py`.

A prova de que o porte e fiel e a mesma que o RTK usa: cada TOML traz casos de
teste embutidos (`[[tests.<filtro>]]`), e `verificar()` roda todos eles contra
este motor.
"""

from .motor import (
    Filtro, aplicar, carregar, carregar_embutidos, achar, verificar, ErroDeFiltro,
)

__all__ = ["Filtro", "aplicar", "carregar", "carregar_embutidos", "achar", "verificar", "ErroDeFiltro"]
