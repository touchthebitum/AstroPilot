from decision.filtering.target_semantics_resolver import (
    TargetSemanticsResolver,
)


def test_ic1396_semantics_are_enriched_from_knowledge():
    target_type, target_subtype = (
        TargetSemanticsResolver.resolve(
            target_name="IC1396",
            catalog_data={
                "type": "nebula",
            },
        )
    )

    assert target_type == "nebula"
    assert target_subtype == "emission"


def test_legacy_emission_nebula_type_is_normalized():
    target_type, target_subtype = (
        TargetSemanticsResolver.resolve(
            target_name="Rosette",
            catalog_data={
                "type": "emission_nebula",
            },
        )
    )

    assert target_type == "nebula"
    assert target_subtype == "emission"


def test_unknown_target_keeps_catalog_semantics():
    target_type, target_subtype = (
        TargetSemanticsResolver.resolve(
            target_name="UnknownTarget",
            catalog_data={
                "type": "planetary_nebula",
            },
        )
    )

    assert target_type == "planetary_nebula"
    assert target_subtype is None