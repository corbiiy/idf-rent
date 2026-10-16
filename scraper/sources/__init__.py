"""One module per source, discovered automatically. Each module exposes:

    SLUG: str                       short id, also the module name
    LABEL: str                      display name for the site
    COLOR: str                      hex colour for the source badge
    MIN_INTERVAL: int (optional)    seconds between two crawls of this source (default: every cycle)
    fetch(session, departments: list[str], max_pages: int) -> Iterator[Listing]
    is_live(session, listing) -> bool | None   (None = could not tell)
"""
from __future__ import annotations

import importlib
import pkgutil

SOURCES = {}
for _info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
    if _info.name.startswith("_"):
        continue
    _mod = importlib.import_module(f"{__name__}.{_info.name}")
    if hasattr(_mod, "SLUG") and hasattr(_mod, "fetch"):
        SOURCES[_mod.SLUG] = _mod
