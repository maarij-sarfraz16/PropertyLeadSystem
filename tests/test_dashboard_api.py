from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.main import _lead_detail, _lead_summary, app, build_dashboard_payload
from app.db.models import Lead, LeadSource, Photo, RawPost, Source

client = TestClient(app)


def test_dashboard_overview_returns_payload():
    response = client.get("/api/dashboard/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]
    assert payload["leads"]
    assert payload["sources"]
    assert payload["notifications"]
    assert payload["feed"]
    assert payload["scoring"]
    assert payload["pipeline"]


def test_build_dashboard_payload_includes_live_stats_and_scoring():
    payload = build_dashboard_payload(
        total_leads=2,
        total_posts=10,
        total_sources=3,
        last_post=datetime(2026, 7, 31, 10, 15, tzinfo=UTC),
        leads=[
            {
                "id": "lead-1",
                "location_text": "DHA Phase 6, Lahore",
                "price": 62500000,
                "bedrooms": 5,
                "seller_type": "owner",
                "score": 98,
                "status": "new",
                "description": "Luxury house",
                "last_seen_at": datetime(2026, 7, 31, 10, 0, tzinfo=UTC),
            },
            {
                "id": "lead-2",
                "location_text": "Clifton, Karachi",
                "price": 34800000,
                "bedrooms": 3,
                "seller_type": "agent",
                "score": 92,
                "status": "reviewed",
                "description": "Apartment",
                "last_seen_at": datetime(2026, 7, 31, 9, 30, tzinfo=UTC),
            },
        ],
        sources=[{"name": "Zameen", "enabled": True}],
    )

    assert payload["metrics"][0]["label"] == "Total Leads Found"
    assert payload["metrics"][0]["value"] == 2
    assert payload["scoring"][0]["score"] == 98
    assert payload["pipeline"][0]["label"] == "Scraping"
    # The dashboard renders no charts; the payload must not carry chart aggregates.
    assert "analytics" not in payload
    # Insights still derive from the counters kept for them.
    assert any("Lahore" in insight for insight in payload["insights"])


def test_lead_serialization_uses_backend_fields():
    source = Source(name="zameen", type="portal", config={})
    raw_post = RawPost(
        source=source,
        external_id="post-1",
        url="https://example.com/listing/1",
        raw_json={
            "title": "10 Marla House in DHA",
            "propertyType": "house",
            "images": ["https://example.com/image-1.jpg"],
        },
        text="Beautiful house in DHA",
        scraped_at=datetime(2026, 7, 31, 11, 0, tzinfo=UTC),
    )
    lead = Lead(
        location_text="DHA Phase 6, Lahore",
        price=62500000,
        area_value=10,
        area_unit="marla",
        bedrooms=5,
        seller_type="owner",
        description="Beautiful house in DHA",
        score=98,
        status="new",
        first_seen_at=datetime(2026, 7, 31, 10, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 7, 31, 11, 0, tzinfo=UTC),
        contact_name="Ali",
        contact_phone="03001234567",
    )
    lead.sources = [LeadSource(raw_post=raw_post)]
    lead.photos = [Photo(url="https://example.com/thumb.jpg")]

    summary = _lead_summary(lead)
    detail = _lead_detail(lead)

    assert summary["title"] == "10 Marla House in DHA"
    assert summary["propertyType"] == "House"
    assert summary["thumbnail"] == "https://example.com/thumb.jpg"
    assert summary["source"] == "Zameen"
    assert summary["originalListingUrl"] == "https://example.com/listing/1"
    assert detail["images"]
    assert detail["aiDetails"]["sellerType"] == "owner"
