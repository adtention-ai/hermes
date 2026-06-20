"""ADtention for Hermes.

A Hermes plugin that decorates Telegram/Discord wait-state messages with a
privacy-preserving sponsor segment. Public entrypoint: ``register``.
"""

from .plugin import register

__all__ = ["register"]
