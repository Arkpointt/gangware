"""
Deprecated module shim for backward compatibility.

Per the engineering blueprint, search and inventory automation live under
`gangware.features.combat`. This module remains temporarily to avoid breaking
imports and will be removed in a future cleanup.

Use `gangware.features.combat.search_service` instead.
"""
from __future__ import annotations

import warnings as _warnings

# Re-export canonical implementation
from ..combat.search_service import SearchService as _SearchService

__all__ = ["SearchService"]


class SearchService(_SearchService):
    """Compatibility wrapper around the canonical SearchService.

    Emits a DeprecationWarning to guide callers to the new module path.
    """

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[override]
        _warnings.warn(
            (
                "gangware.features.search.search_service is deprecated; "
                "use gangware.features.combat.search_service instead."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)
