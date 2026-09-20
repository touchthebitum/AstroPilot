from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from astropilot.file_lock import exclusive_file_lock

from decision.acceptance_lineage_persistence import (
    AcceptanceRequestMapping,
    AcceptanceLineageConflictError,
    AcceptanceLineageCorruptionError,
    AcceptanceLineageNotFoundError,
    DecisionAcceptanceAggregate,
    deserialize_decision_acceptance_aggregate,
    serialize_decision_acceptance_aggregate,
    validate_lineage_identity,
)
from decision.mission.night_mission import NightMission
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.services.decision_acceptance_application import (
    DecisionAcceptanceContext,
)


class FileDecisionAcceptanceLineageStore:
    def __init__(self, directory: Path):
        self._directory = Path(directory)

    def _path(self, decision_id: str) -> Path:
        identity = validate_lineage_identity(decision_id, field="decision_id")
        return self._directory / f"{identity}.json"

    def _locked(self):
        return exclusive_file_lock(
            self._directory / ".decision_lineage.lock"
        )

    def _load_path(self, path: Path) -> DecisionAcceptanceAggregate:
        try:
            document = path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise AcceptanceLineageNotFoundError(
                "decision_context_not_found"
            ) from error
        except UnicodeError as error:
            raise AcceptanceLineageCorruptionError(
                "invalid_json_document"
            ) from error
        try:
            return deserialize_decision_acceptance_aggregate(
                document,
                decision_id=path.stem,
            )
        except AcceptanceLineageCorruptionError:
            raise
        except (TypeError, ValueError) as error:
            raise AcceptanceLineageCorruptionError(
                "invalid_lineage_aggregate"
            ) from error

    def _load_all(self) -> list[DecisionAcceptanceAggregate]:
        if not self._directory.exists():
            return []
        return [
            self._load_path(path)
            for path in sorted(self._directory.glob("*.json"))
        ]

    def _write(self, aggregate: DecisionAcceptanceAggregate) -> None:
        path = self._path(aggregate.decision_id)
        document = serialize_decision_acceptance_aggregate(aggregate)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._directory,
                prefix=f".{aggregate.decision_id}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(document)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                primary_error = sys.exception()
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    if primary_error is None:
                        raise

    def create_context(self, context: DecisionAcceptanceContext) -> None:
        if type(context) is not DecisionAcceptanceContext:
            raise AcceptanceLineageCorruptionError(
                "invalid_decision_acceptance_context"
            )
        decision_id = context.decision_context.decision_id
        path = self._path(decision_id)
        with self._locked():
            if path.exists():
                existing = self._load_path(path)
                if existing.context == context:
                    return
                raise AcceptanceLineageConflictError(
                    "decision_context_conflict"
                )
            self._write(DecisionAcceptanceAggregate(context=context))

    def save(self, context: DecisionAcceptanceContext) -> None:
        self.create_context(context)

    def load_context(self, decision_id: str) -> DecisionAcceptanceContext:
        path = self._path(decision_id)
        if not path.exists():
            raise AcceptanceLineageNotFoundError("decision_context_not_found")
        return self._load_path(path).context

    def load(
        self,
        *,
        decision_id: str,
    ) -> DecisionAcceptanceContext | None:
        try:
            return self.load_context(decision_id)
        except AcceptanceLineageNotFoundError:
            return None

    def commit_selection_and_mission(
        self,
        selection: UserSelection,
        mission: NightMission | None,
        *,
        acceptance_request_id: str | None = None,
    ) -> tuple[UserSelection, NightMission | None]:
        if type(selection) is not UserSelection:
            raise AcceptanceLineageCorruptionError("invalid_user_selection")
        if selection.source is UserSelectionSource.DECLINED:
            if mission is not None:
                raise AcceptanceLineageConflictError(
                    "declined_selection_mission_conflict"
                )
        elif type(mission) is not NightMission:
            raise AcceptanceLineageCorruptionError("mission_required")
        if mission is not None and (
            mission.decision_id != selection.decision_id
            or mission.selection_id != selection.selection_id
        ):
            raise AcceptanceLineageConflictError("mission_provenance_mismatch")
        if mission is not None and (
            mission.acquisition_intent_id
            != selection.selected_acquisition_intent_id
        ):
            raise AcceptanceLineageConflictError(
                "mission_acquisition_intent_mismatch"
            )
        request_id = None
        if acceptance_request_id is not None:
            request_id = validate_lineage_identity(
                acceptance_request_id,
                field="acceptance_request_id",
            )

        path = self._path(selection.decision_id)
        with self._locked():
            aggregates = self._load_all()
            if request_id is not None:
                request_matches = [
                    (item, request)
                    for item in aggregates
                    for request in item.acceptance_requests
                    if request.acceptance_request_id == request_id
                ]
                if len(request_matches) > 1:
                    raise AcceptanceLineageConflictError(
                        "acceptance_request_conflict"
                    )
                if request_matches:
                    aggregate, request = request_matches[0]
                    canonical_selection = next(
                        stored
                        for stored in aggregate.selections
                        if stored.selection_id == request.selection_id
                    )
                    canonical_mission = (
                        None
                        if request.mission_id is None
                        else next(
                            stored
                            for stored in aggregate.missions
                            if stored.mission_id == request.mission_id
                        )
                    )
                    if not self._same_acceptance_payload(
                        canonical_selection,
                        selection,
                    ):
                        raise AcceptanceLineageConflictError(
                            "acceptance_request_conflict"
                        )
                    return canonical_selection, canonical_mission
            if not path.exists():
                raise AcceptanceLineageNotFoundError(
                    "decision_context_not_found"
                )
            target = next(
                (
                    item
                    for item in aggregates
                    if item.decision_id == selection.decision_id
                ),
                None,
            )
            if target is None:
                raise AcceptanceLineageNotFoundError(
                    "decision_context_not_found"
                )

            matching_selections = [
                (item, stored)
                for item in aggregates
                for stored in item.selections
                if stored.selection_id == selection.selection_id
            ]
            if matching_selections:
                existing_aggregate, existing_selection = matching_selections[0]
                if (
                    len(matching_selections) != 1
                    or existing_aggregate.decision_id != target.decision_id
                    or existing_selection != selection
                ):
                    raise AcceptanceLineageConflictError(
                        "selection_id_conflict"
                    )

            matching_missions = []
            if mission is not None:
                matching_missions = [
                    (item, stored)
                    for item in aggregates
                    for stored in item.missions
                    if stored.mission_id == mission.mission_id
                ]
                if matching_missions:
                    existing_aggregate, existing_mission = matching_missions[0]
                    if (
                        len(matching_missions) != 1
                        or existing_aggregate.decision_id != target.decision_id
                        or existing_mission != mission
                    ):
                        raise AcceptanceLineageConflictError(
                            "mission_id_conflict"
                        )

            if matching_selections:
                if mission is None and not matching_missions:
                    return selection, None
                if mission is not None and matching_missions:
                    return selection, mission
                raise AcceptanceLineageConflictError(
                    "acceptance_lineage_conflict"
                )
            if matching_missions:
                raise AcceptanceLineageConflictError(
                    "acceptance_lineage_conflict"
                )

            updated = DecisionAcceptanceAggregate(
                context=target.context,
                selections=target.selections + (selection,),
                missions=(
                    target.missions
                    if mission is None
                    else target.missions + (mission,)
                ),
                acceptance_requests=(
                    target.acceptance_requests
                    if request_id is None
                    else target.acceptance_requests + (
                        AcceptanceRequestMapping(
                            acceptance_request_id=request_id,
                            selection_id=selection.selection_id,
                            mission_id=(
                                None if mission is None else mission.mission_id
                            ),
                        ),
                    )
                ),
            )
            self._write(updated)
            return selection, mission

    @staticmethod
    def _same_acceptance_payload(
        left: UserSelection,
        right: UserSelection,
    ) -> bool:
        return (
            left.decision_id,
            left.source,
            left.selected_catalog_key,
            left.selected_at,
            left.selected_acquisition_intent_id,
        ) == (
            right.decision_id,
            right.source,
            right.selected_catalog_key,
            right.selected_at,
            right.selected_acquisition_intent_id,
        )

    def load_acceptance(
        self,
        acceptance_request_id: str,
    ) -> tuple[UserSelection, NightMission | None] | None:
        request_id = validate_lineage_identity(
            acceptance_request_id,
            field="acceptance_request_id",
        )
        matches = [
            (aggregate, request)
            for aggregate in self._load_all()
            for request in aggregate.acceptance_requests
            if request.acceptance_request_id == request_id
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise AcceptanceLineageConflictError(
                "acceptance_request_conflict"
            )
        aggregate, request = matches[0]
        canonical_selection = next(
            stored
            for stored in aggregate.selections
            if stored.selection_id == request.selection_id
        )
        canonical_mission = (
            None
            if request.mission_id is None
            else next(
                stored
                for stored in aggregate.missions
                if stored.mission_id == request.mission_id
            )
        )
        return canonical_selection, canonical_mission

    def load_selection(self, selection_id: str) -> UserSelection:
        identity = validate_lineage_identity(selection_id, field="selection_id")
        matches = [
            selection
            for aggregate in self._load_all()
            for selection in aggregate.selections
            if selection.selection_id == identity
        ]
        if not matches:
            raise AcceptanceLineageNotFoundError("selection_not_found")
        if len(matches) != 1:
            raise AcceptanceLineageConflictError("selection_id_conflict")
        return matches[0]

    def load_mission(self, mission_id: str) -> NightMission:
        identity = validate_lineage_identity(mission_id, field="mission_id")
        matches = [
            mission
            for aggregate in self._load_all()
            for mission in aggregate.missions
            if mission.mission_id == identity
        ]
        if not matches:
            raise AcceptanceLineageNotFoundError("mission_not_found")
        if len(matches) != 1:
            raise AcceptanceLineageConflictError("mission_id_conflict")
        return matches[0]
