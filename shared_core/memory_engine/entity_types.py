from enum import Enum

class EntityType(str, Enum):
    PERSON = "Person"
    PROJECT = "Project"
    FILE = "File"
    APP = "App"
    COMMAND = "Command"
    TOOL = "Tool"
    EVENT = "Event"
    HABIT = "Habit"
    CONCEPT = "Concept"
