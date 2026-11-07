"""Parse the Yes/No attestation answer into yes, no, or unparsed."""
from __future__ import annotations

import re

_PUNCT = r"""[\s*_`"'“”‘’.!]*"""
_ANSWER = re.compile(rf"^{_PUNCT}(yes|no){_PUNCT}$", re.IGNORECASE)


def parse(raw: str | None) -> str:
    if not raw:
        return "unparsed"
    m = _ANSWER.match(raw)
    return m.group(1).lower() if m else "unparsed"
