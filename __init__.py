"""Root Hermes directory-plugin entrypoint."""

try:  # Hermes directory-plugin loader imports as hermes_plugins.<slug>.
    from .adtention_hermes.plugin import register
except ImportError:  # Pytest may import the repo root as a top-level __init__.
    from adtention_hermes.plugin import register

__all__ = ["register"]
