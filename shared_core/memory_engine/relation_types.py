from enum import Enum

class RelationType(str, Enum):
    WORKS_ON = "works_on"
    EDITS = "edits"
    DEPENDS_ON = "depends_on"
    PRECEDES = "precedes"
    AUTHORED_BY = "authored_by"
    LOCATED_IN = "located_in"
    INSTANCE_OF = "instance_of"
