from pathlib import Path
import json


KNOWLEDGE_ROOT = Path(__file__).parent / "knowledge"


class KnowledgeEngine:
    """
    Charge et expose la base de connaissances AstroPilot.
    Ne prend aucune décision.
    Ne score rien.
    Il fournit seulement des connaissances structurées.
    """

    def __init__(self, root=KNOWLEDGE_ROOT):
        self.root = Path(root)

    def load_json(self, relative_path):
        path = self.root / relative_path

        if not path.exists():
            raise FileNotFoundError(f"Knowledge file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_object(self, object_id):
        return self.load_json(f"objects/{object_id}.json")

    def get_filter(self, filter_id):
        return self.load_json(f"filters/{filter_id}.json")

    def get_equipment(self, equipment_id):
        return self.load_json(f"equipment/{equipment_id}.json")

    def get_site(self, site_id):
        return self.load_json(f"sites/{site_id}.json")

    def get_rule(self, rule_id):
        return self.load_json(f"rules/{rule_id}.json")

    def list_objects(self):
        folder = self.root / "objects"

        return sorted(
            f.stem
            for f in folder.glob("*.json")
        )

    def search_objects(self, **criteria):
        results = []

        for object_id in self.list_objects():
            obj = self.get_object(object_id)

            keep = True

            for key, value in criteria.items():
                if key == "month":
                    if value not in obj.get("best_months", []):
                        keep = False
                        break

                elif obj.get(key) != value:
                    keep = False
                    break
            if key == "month":
                if value not in obj.get("best_months", []):
                    keep = False
                    break

            elif obj.get(key) != value:
                keep = False
                break

            if keep:
                results.append(obj)

        return results
    