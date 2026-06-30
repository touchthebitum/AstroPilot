from abc import ABC, abstractmethod


class BaseRule(ABC):
    """
    Classe de base pour toutes les règles du DecisionEngine.
    """

    @abstractmethod
    def evaluate(self, project, context):
        pass