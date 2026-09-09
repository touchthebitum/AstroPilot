from dataclasses import dataclass
from enum import Enum


class PresentationDepth(str, Enum):
    CLASSIC = "classic"
    PRO = "pro"


@dataclass(frozen=True, slots=True)
class RecommendationReasonRendering:
    presentation_key: str
    depth: PresentationDepth
    text: str
