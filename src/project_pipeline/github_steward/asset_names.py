"""Canonical names for GitHub release assets.

GitHub normalizes some uploaded names (notably whitespace) before returning
them from the release API.  Release integrity therefore binds the normalized,
portable spelling rather than trusting a local filesystem spelling.
"""

from __future__ import annotations

import re
import unicodedata

_SAFE_ASSET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,239}$")


def canonical_release_asset_name(value: str) -> str:
    """Return the single portable spelling used for a release asset.

    The transformation deliberately matches GitHub's historical whitespace
    sanitization (spaces become dots), rejects directory components, and keeps
    the remaining vocabulary within the cross-platform filename subset.  This
    function is used for the local manifest, GitHub writes, GitHub readback,
    and acquired remote-byte filenames.
    """

    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized or "/" in normalized or "\\" in normalized:
        raise ValueError("release asset name must be one filename")
    normalized = re.sub(r"\s+", ".", normalized)
    normalized = re.sub(r"[^A-Za-z0-9._+-]", ".", normalized)
    normalized = re.sub(r"\.{2,}", ".", normalized).strip(".")
    if not _SAFE_ASSET_NAME.fullmatch(normalized):
        raise ValueError("release asset name is not portable after normalization")
    return normalized
