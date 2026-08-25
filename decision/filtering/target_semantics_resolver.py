import json
from pathlib import Path


class TargetSemanticsResolver:
    KNOWLEDGE_ROOT = (
        Path(__file__).resolve().parents[2]
        / "astropilot"
        / "knowledge"
        / "objects"
    )

    @staticmethod
    def resolve(
        target_name: str,
        catalog_data: dict,
    ) -> tuple[str, str | None]:
        target_type = catalog_data.get("type", "")
        target_subtype = catalog_data.get("subtype")

        knowledge_path = (
            TargetSemanticsResolver.KNOWLEDGE_ROOT
            / f"{target_name.lower()}.json"
        )

        if knowledge_path.exists():
            with knowledge_path.open(
                "r",
                encoding="utf-8",
            ) as handle:
                knowledge = json.load(handle)

            target_type = knowledge.get(
                "type",
                target_type,
            )

            target_subtype = knowledge.get(
                "subtype",
                target_subtype,
            )

        # Normalisation des anciens types du catalogue.
        if target_type == "emission_nebula":
            target_type = "nebula"
            target_subtype = "emission"

        return target_type, target_subtype