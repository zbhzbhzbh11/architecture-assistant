import pytest
from services.matching_agent.app.main import score_style

def test_score_style_layered():
    style = {
        "name": "Layered Architecture",
        "tags": ["complex_business", "strict_consistency"]
    }
    features = {"complex_business": True, "strict_consistency": True}
    result = score_style(style, features)
    
    # Base tags score (2 * 2 = 4) + Extra rule (1) = 5
    assert result["score"] == 5
    assert "matches feature: complex_business" in result["reasons"]
    assert "extra rule: strict consistency fits layered core domain" in result["reasons"]

def test_score_style_event_driven():
    style = {
        "name": "Event-Driven Architecture",
        "tags": ["high_concurrency", "real_time"]
    }
    features = {"high_concurrency": True, "real_time": True}
    result = score_style(style, features)
    
    # Base tags score (2 * 2 = 4) + Extra rule (1) = 5
    assert result["score"] == 5
    assert "extra rule: high concurrency favors event-driven" in result["reasons"]
