from enum import Enum


class Action(str, Enum):
    CONTINUE_PROJECT = "continue_project"
    START_PROJECT = "start_project"