"""Photo URL repair.

Guards a bug that made every thumbnail in the dashboard render as a placeholder: Zameen's API
returns the private S3 object path for each photo, and that bucket answers 403.
"""
from __future__ import annotations

import pytest

from app.pipeline.photos import public_photo_url, public_photo_urls

S3 = "https://zameen-dev.s3.eu-west-1.amazonaws.com/image/305575431/e84e03b32d114338a04c4cc7055be6d4"
CDN = "https://media.zameen.com/thumbnails/305575431-800x600.jpeg"


def test_zameen_s3_path_becomes_a_cdn_rendition():
    assert public_photo_url(S3) == CDN


def test_repair_is_idempotent():
    assert public_photo_url(CDN) == CDN


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/photo.jpg",
        "https://media.zameen.com/thumbnails/1-400x300.jpeg",
        # Not the recognised shape: rewriting it would be a guess.
        "https://zameen-dev.s3.eu-west-1.amazonaws.com/video/12/abc",
    ],
)
def test_unrecognised_urls_pass_through_untouched(url):
    assert public_photo_url(url) == url


@pytest.mark.parametrize("value", [None, ""])
def test_blank_input_yields_nothing(value):
    assert public_photo_url(value) is None


def test_list_repair_drops_blanks_and_preserves_order():
    assert public_photo_urls([S3, "", "https://example.com/a.jpg"]) == [
        CDN,
        "https://example.com/a.jpg",
    ]


def test_list_repair_collapses_the_two_forms_of_one_photo():
    """The raw payload's S3 cover and the stored CDN copy are the same image, not two."""
    assert public_photo_urls([S3, CDN]) == [CDN]
