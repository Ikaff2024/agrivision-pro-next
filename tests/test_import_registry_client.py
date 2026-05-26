from app.importers.cooperative_registry import parse_registry


def test_parse_client_yeyasso_2025_registry():
    result = parse_registry(
        "docs/Registre FT YEYASSO 2025-2026 Act .xlsx",
        filename="Registre FT YEYASSO 2025-2026 Act .xlsx",
    )

    assert result.errors == []
    assert result.detected_campaign == "2025-2026"
    assert len(result.producers) > 6900
    assert len(result.plantations) > 7000
    assert result.producers[0].code_yeyasso == "YEYAFT001"
    assert result.plantations[0].code_plantation == "YEYAFT001-P1"
    assert "formations" in result.summary()
