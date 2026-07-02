from abc import ABC, abstractmethod

from decision.models.engine_result import EngineResult


class BaseEngine(ABC):
    """
    Base class for every AstroPilot engine.

    Every engine analyses a specific domain and returns a standardized
    EngineResult that can be consumed by higher-level decision engines.
    """

    @abstractmethod
    def evaluate(self, context) -> EngineResult:
        """
        Analyse the provided context and return a standardized result.
        """
        pass