"""Photo URL repair.

Zameen's listing API hands back the *storage* location of each photo — a
`zameen-dev.s3.eu-west-1.amazonaws.com/image/<id>/<blob>` path whose bucket is not public and
answers every request with 403. The URL a browser can actually load is the CDN's rendition:
`media.zameen.com/thumbnails/<id>-<width>x<height>.jpeg`, keyed by the same numeric image id.

Stored verbatim, those S3 links turn every thumbnail in the dashboard into a placeholder. This
sits alongside `app.pipeline.urls` — same job, same rule: repair what can be repaired, and pass
anything unrecognised through untouched rather than guessing.
"""
from __future__ import annotations

import re

# .../image/<numeric id>/<blob>, the only form the search API has been observed to return.
_ZAMEEN_S3 = re.compile(
    r"^https?://zameen-dev\.s3[.-][\w-]+\.amazonaws\.com/image/(\d+)/[0-9a-f]+/?$",
    re.IGNORECASE,
)

# Large enough for the detail gallery, small enough for a list thumbnail. One stored URL serves
# both, so a single rendition avoids having to know at ingest where it will be displayed.
_RENDITION = "800x600"


def public_photo_url(url: str | None) -> str | None:
    """A browser-loadable URL for a photo, or the input unchanged when no repair applies."""
    if not url:
        return None
    match = _ZAMEEN_S3.match(url.strip())
    if match is None:
        return url
    return f"https://media.zameen.com/thumbnails/{match.group(1)}-{_RENDITION}.jpeg"


def public_photo_urls(urls: list[str]) -> list[str]:
    """Repair a list of photo URLs, dropping blanks and preserving order without duplicates."""
    out: list[str] = []
    for url in urls:
        repaired = public_photo_url(url)
        if repaired and repaired not in out:
            out.append(repaired)
    return out
