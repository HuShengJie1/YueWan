from enum import StrEnum

from sqlalchemy import Enum


class GroupMemberRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class GroupMemberStatus(StrEnum):
    ACTIVE = "active"
    LEFT = "left"


class HangoutStatus(StrEnum):
    DRAFT = "draft"
    VOTING = "voting"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    FINISHED = "finished"


class ProposalVoteValue(StrEnum):
    LIKE = "LIKE"
    OK = "OK"
    DISLIKE = "DISLIKE"


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    """Persist enum values instead of Python member names."""
    return [member.value for member in enum_type]


def persisted_enum(enum_type: type[StrEnum], *, name: str) -> Enum:
    """Store enums as VARCHAR values; table models own the explicit checks."""
    values = enum_values(enum_type)
    return Enum(
        enum_type,
        name=name,
        values_callable=enum_values,
        validate_strings=True,
        native_enum=False,
        create_constraint=False,
        length=max(len(value) for value in values),
    )
