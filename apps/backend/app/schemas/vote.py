from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator

from app.models.enums import HangoutStatus, ProposalVoteValue
from app.repositories.vote import ProposalVoteSummary, TimeVoteSummary
from app.services.vote import VotingSummary


class ProposalVoteWrite(BaseModel):
    value: ProposalVoteValue

    model_config = ConfigDict(extra="forbid")


class TimeVoteReplace(BaseModel):
    time_option_ids: list[UUID]

    model_config = ConfigDict(extra="forbid")


class ProposalVoteCounts(BaseModel):
    LIKE: int
    OK: int
    DISLIKE: int


class ProposalVotingRead(BaseModel):
    id: UUID
    submitted_by_user_id: UUID
    title: str
    description: str | None
    location_text: str | None
    external_platform: str | None
    external_url: str | None
    external_data: dict[str, JsonValue] | None
    created_at: datetime
    updated_at: datetime
    vote_counts: ProposalVoteCounts
    current_user_vote: ProposalVoteValue | None

    @classmethod
    def from_summary(cls, summary: ProposalVoteSummary) -> "ProposalVotingRead":
        proposal = summary.proposal
        return cls(
            id=proposal.id,
            submitted_by_user_id=proposal.submitted_by_user_id,
            title=proposal.title,
            description=proposal.description,
            location_text=proposal.location_text,
            external_platform=proposal.external_platform,
            external_url=proposal.external_url,
            external_data=proposal.external_data,
            created_at=proposal.created_at,
            updated_at=proposal.updated_at,
            vote_counts=ProposalVoteCounts(
                LIKE=summary.like_count,
                OK=summary.ok_count,
                DISLIKE=summary.dislike_count,
            ),
            current_user_vote=summary.current_user_vote,
        )

    @field_validator("created_at", "updated_at")
    @classmethod
    def serialize_dates_as_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class TimeVotingRead(BaseModel):
    id: UUID
    created_by_user_id: UUID
    starts_at: datetime
    ends_at: datetime | None
    display_label: str | None
    created_at: datetime
    updated_at: datetime
    availability_count: int
    current_user_selected: bool

    @classmethod
    def from_summary(cls, summary: TimeVoteSummary) -> "TimeVotingRead":
        time_option = summary.time_option
        return cls(
            id=time_option.id,
            created_by_user_id=time_option.created_by_user_id,
            starts_at=time_option.starts_at,
            ends_at=time_option.ends_at,
            display_label=time_option.display_label,
            created_at=time_option.created_at,
            updated_at=time_option.updated_at,
            availability_count=summary.availability_count,
            current_user_selected=summary.current_user_selected,
        )

    @field_validator("starts_at", "ends_at", "created_at", "updated_at")
    @classmethod
    def serialize_dates_as_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(UTC)


class TimeVoteListData(BaseModel):
    time_options: list[TimeVotingRead]


class VotingSummaryRead(TimeVoteListData):
    hangout_id: UUID
    status: HangoutStatus
    voting_deadline: datetime | None
    proposals: list[ProposalVotingRead]

    @classmethod
    def from_summary(cls, summary: VotingSummary) -> "VotingSummaryRead":
        return cls(
            hangout_id=summary.hangout.id,
            status=summary.hangout.status,
            voting_deadline=summary.hangout.voting_deadline,
            proposals=[ProposalVotingRead.from_summary(item) for item in summary.proposals],
            time_options=[TimeVotingRead.from_summary(item) for item in summary.time_options],
        )

    @field_validator("voting_deadline")
    @classmethod
    def serialize_deadline_as_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(UTC)
