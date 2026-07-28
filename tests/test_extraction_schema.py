from app.extraction.schema import ExtractedLead, Intent, SellerType


def test_schema_parses_full_json():
    data = {
        "is_property_listing": True,
        "intent": "sell",
        "location_text": "DHA Phase 5, Lahore",
        "price": 47500000,
        "currency": "PKR",
        "area_value": 10,
        "area_unit": "marla",
        "bedrooms": 5,
        "seller_type": "owner",
        "contact_phone": "0300-1234567",
        "contact_name": None,
        "description": "10 marla house",
        "confidence": 0.9,
    }
    lead = ExtractedLead.model_validate(data)
    assert lead.intent is Intent.sell
    assert lead.seller_type is SellerType.owner
    assert lead.price == 47500000


def test_defaults_for_noise_post():
    lead = ExtractedLead.model_validate({"is_property_listing": False})
    assert lead.is_property_listing is False
    assert lead.intent is Intent.unknown
    assert lead.confidence == 0.0
