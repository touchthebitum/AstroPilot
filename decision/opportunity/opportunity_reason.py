from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpportunityReason:
    title: str
    message: str
