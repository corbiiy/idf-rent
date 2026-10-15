"""One module per source. Each exposes:

    SLUG: str
    LABEL: str
    fetch(session, departments: list[str], max_pages: int) -> Iterator[Listing]
    is_live(session, listing) -> bool | None   (None = could not tell)
"""
from . import bienici, pap

SOURCES = {m.SLUG: m for m in (bienici, pap)}
