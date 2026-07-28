from app.sources.base import RawPostData
from app.sources.zameen import ZameenAdapter


def test_fixture_fetch_normalizes():
    posts = ZameenAdapter(use_fixtures=True).fetch(limit=50)
    assert len(posts) == 6
    assert all(isinstance(p, RawPostData) for p in posts)
    first = posts[0]
    assert first.external_id == "zm-1001"
    assert "DHA Phase 5" in first.text
    assert first.photo_urls  # has images


def test_limit_respected():
    assert len(ZameenAdapter(use_fixtures=True).fetch(limit=2)) == 2
