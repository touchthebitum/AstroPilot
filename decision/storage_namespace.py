"""Domain boundary shared by user decoders and Field Lab persistence."""
from collections.abc import Mapping

FIELD_LAB_PROVENANCE = "field_lab_reference_station"


def is_field_lab_document(value):
    if isinstance(value, Mapping):
        if any(value.get(key) == FIELD_LAB_PROVENANCE
               for key in ("namespace", "provenance", "source_type")):
            return True
        return any(is_field_lab_document(item) for item in value.values())
    if isinstance(value, list):
        return any(is_field_lab_document(item) for item in value)
    return False


def require_user_document(value, error_type=ValueError):
    if is_field_lab_document(value):
        raise error_type("field_lab_document_excluded")
