from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SetupFilterCapabilities:
    equipment_id: str
    available_filter_types: tuple[str, ...]
    available_filter_profile_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.equipment_id, str):
            raise TypeError("equipment_id must be a string")
        if not self.equipment_id.strip():
            raise ValueError("equipment_id must not be empty")
        if not isinstance(self.available_filter_types, tuple):
            raise TypeError("available_filter_types must be a tuple")
        if not self.available_filter_types:
            raise ValueError("available_filter_types must not be empty")

        seen_filter_types: set[str] = set()
        for filter_type in self.available_filter_types:
            if not isinstance(filter_type, str):
                raise TypeError("filter_type must be a string")
            if not filter_type.strip():
                raise ValueError("filter_type must not be empty")
            if filter_type in seen_filter_types:
                raise ValueError(
                    "available_filter_types must not contain duplicates"
                )
            seen_filter_types.add(filter_type)

        if not isinstance(self.available_filter_profile_ids, tuple):
            raise TypeError(
                "available_filter_profile_ids must be a tuple"
            )

        seen_filter_profile_ids: set[str] = set()
        for filter_profile_id in self.available_filter_profile_ids:
            if not isinstance(filter_profile_id, str):
                raise TypeError("filter_profile_id must be a string")
            if not filter_profile_id.strip():
                raise ValueError("filter_profile_id must not be empty")
            if filter_profile_id in seen_filter_profile_ids:
                raise ValueError(
                    "available_filter_profile_ids must not contain duplicates"
                )
            seen_filter_profile_ids.add(filter_profile_id)
