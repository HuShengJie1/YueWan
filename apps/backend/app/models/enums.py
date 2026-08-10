from enum import StrEnum


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
