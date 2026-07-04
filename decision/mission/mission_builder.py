from decision.mission.night_mission import (
    NightMission,
    MissionReason,
)


class NightMissionBuilder:

    @staticmethod
    def build(target, summary):

        reasons = []

        for r in summary.positives:
            reasons.append(
                MissionReason(
                    title=r,
                    severity="success",
                )
            )

        for r in summary.negatives:
            reasons.append(
                MissionReason(
                    title=r,
                    severity="warning",
                )
            )

        return NightMission(
            target=target,
            confidence=summary.confidence,
            reasons=reasons,
        )
