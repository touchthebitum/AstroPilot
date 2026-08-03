from dataclasses import dataclass

from decision.models.candidate import Candidate

from .action import Action


@dataclass(slots=True)
class Opportunity:
    action: Action
    candidate: Candidate