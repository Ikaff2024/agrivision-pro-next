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


def test_parse_plantation_only_registry_synthesizes_producers():
    """Registre centre plantations (sans feuille producteurs) : les producteurs
    sont deduits des codes, l'import ne doit pas echouer (cas Coop test 2)."""
    result = parse_registry(
        "docs/Registre FT Coop test 2 2025-2026 Act.xlsx",
        filename="Registre FT Coop test 2 2025-2026 Act.xlsx",
    )
    assert result.errors == []                       # plus d'erreur bloquante
    assert len(result.plantations) > 100
    # autant de producteurs deduits que de codes producteurs distincts
    assert len(result.producers) == len(result.plantations)
    assert result.producers[0].code_yeyasso == "PROD0001"
    assert result.producers[0].nom_complet == "PROD0001"   # nom provisoire = code
    assert result.producers[0].projet == "FT-RA"           # certification conservee
