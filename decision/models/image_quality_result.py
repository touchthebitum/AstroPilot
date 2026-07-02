from dataclasses import dataclass


@dataclass
class ImageQualityResult:

    score: float

    sampling_score: float
    resolution_score: float

    adequacy: float

    pixels: float
    size_factor: str

    ratio: float

    detail_level: str

    limiting_factor: str

    recommendation: str
