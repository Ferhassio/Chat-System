from enum import Enum

class MessageDirection(str, Enum):
    """Message direction enum"""
    INCOMING = "incoming"
    OUTGOING = "outgoing" 