from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    GroupNotFoundError,
    HangoutNotFoundError,
    ProposalManageForbiddenError,
    ProposalNotFoundError,
    ProposalStateConflictError,
)
from app.core.group_security import ProposalPageCursor, SignedCursorCodec
from app.models.enums import GroupMemberRole, HangoutStatus
from app.models.group import GroupMember
from app.models.hangout import Hangout
from app.models.proposal import Proposal
from app.models.user import User
from app.repositories.proposal import ProposalRepository


@dataclass(frozen=True, slots=True)
class ManagedProposal:
    proposal: Proposal
    can_manage: bool


@dataclass(frozen=True, slots=True)
class ProposalPage:
    items: list[ManagedProposal]
    next_cursor: str | None
    has_more: bool


class ProposalService:
    """Apply proposal visibility/management rules and own write transactions."""

    def __init__(self, *, repository: ProposalRepository, cursors: SignedCursorCodec) -> None:
        self._proposals = repository
        self._cursors = cursors

    async def create_proposal(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        title: str,
        description: str | None,
        location_text: str | None,
        external_platform: str | None,
        external_url: str | None,
        external_data: dict[str, Any] | None,
    ) -> ManagedProposal:
        try:
            membership = await self._proposals.get_active_membership_for_update(
                group_id=group_id,
                user_id=current_user.id,
            )
            if membership is None:
                raise GroupNotFoundError
            hangout = await self._proposals.get_hangout_for_update(
                group_id=group_id,
                hangout_id=hangout_id,
            )
            if hangout is None:
                raise HangoutNotFoundError
            self._require_draft(hangout)
            proposal = await self._proposals.create(
                hangout_id=hangout_id,
                submitted_by_user_id=current_user.id,
                title=title.strip(),
                description=self._normalize_optional_text(description),
                location_text=self._normalize_optional_text(location_text),
                external_platform=self._normalize_optional_text(external_platform),
                external_url=self._normalize_optional_text(external_url),
                external_data=external_data,
            )
            await self._proposals.commit()
        except IntegrityError as exc:
            await self._proposals.rollback()
            raise ProposalStateConflictError from exc
        except Exception:
            await self._proposals.rollback()
            raise
        return ManagedProposal(proposal=proposal, can_manage=True)

    async def list_proposals(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> ProposalPage:
        membership, hangout = await self._require_read_context(
            current_user,
            group_id=group_id,
            hangout_id=hangout_id,
        )
        scope = self._cursor_scope(group_id=group_id, hangout_id=hangout_id)
        after = (
            cast(
                ProposalPageCursor,
                self._cursors.decode(cursor, kind="proposal_list", scope=scope),
            )
            if cursor is not None
            else None
        )
        rows = await self._proposals.list_in_hangout(
            hangout_id=hangout_id,
            after=after,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        proposals = rows[:limit]
        items = [
            ManagedProposal(
                proposal=proposal,
                can_manage=self._can_manage(
                    current_user=current_user,
                    membership=membership,
                    hangout=hangout,
                    proposal=proposal,
                ),
            )
            for proposal in proposals
        ]
        next_cursor = None
        if has_more and proposals:
            last = proposals[-1]
            next_cursor = self._cursors.encode(
                ProposalPageCursor(created_at=last.created_at, proposal_id=last.id),
                kind="proposal_list",
                scope=scope,
            )
        return ProposalPage(items=items, next_cursor=next_cursor, has_more=has_more)

    async def update_proposal(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        proposal_id: UUID,
        title: str,
        description: str | None,
        location_text: str | None,
        external_platform: str | None,
        external_url: str | None,
        external_data: dict[str, Any] | None,
    ) -> ManagedProposal:
        try:
            membership, hangout, proposal = await self._lock_write_context(
                current_user,
                group_id=group_id,
                hangout_id=hangout_id,
                proposal_id=proposal_id,
            )
            self._require_draft(hangout)
            self._require_manage_permission(
                current_user=current_user,
                membership=membership,
                hangout=hangout,
                proposal=proposal,
            )
            updated = await self._proposals.update(
                proposal,
                title=title.strip(),
                description=self._normalize_optional_text(description),
                location_text=self._normalize_optional_text(location_text),
                external_platform=self._normalize_optional_text(external_platform),
                external_url=self._normalize_optional_text(external_url),
                external_data=external_data,
            )
            await self._proposals.commit()
        except IntegrityError as exc:
            await self._proposals.rollback()
            raise ProposalStateConflictError from exc
        except Exception:
            await self._proposals.rollback()
            raise
        return ManagedProposal(proposal=updated, can_manage=True)

    async def delete_proposal(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        proposal_id: UUID,
    ) -> None:
        try:
            membership, hangout, proposal = await self._lock_write_context(
                current_user,
                group_id=group_id,
                hangout_id=hangout_id,
                proposal_id=proposal_id,
            )
            self._require_draft(hangout)
            self._require_manage_permission(
                current_user=current_user,
                membership=membership,
                hangout=hangout,
                proposal=proposal,
            )
            await self._proposals.delete(proposal)
            await self._proposals.commit()
        except IntegrityError as exc:
            await self._proposals.rollback()
            raise ProposalStateConflictError from exc
        except Exception:
            await self._proposals.rollback()
            raise

    async def _require_read_context(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
    ) -> tuple[GroupMember, Hangout]:
        membership = await self._proposals.get_active_membership(
            group_id=group_id,
            user_id=current_user.id,
        )
        if membership is None:
            raise GroupNotFoundError
        hangout = await self._proposals.get_hangout(
            group_id=group_id,
            hangout_id=hangout_id,
        )
        if hangout is None:
            raise HangoutNotFoundError
        return membership, hangout

    async def _lock_write_context(
        self,
        current_user: User,
        *,
        group_id: UUID,
        hangout_id: UUID,
        proposal_id: UUID,
    ) -> tuple[GroupMember, Hangout, Proposal]:
        membership = await self._proposals.get_active_membership_for_update(
            group_id=group_id,
            user_id=current_user.id,
        )
        if membership is None:
            raise GroupNotFoundError
        hangout = await self._proposals.get_hangout_for_update(
            group_id=group_id,
            hangout_id=hangout_id,
        )
        if hangout is None:
            raise HangoutNotFoundError
        proposal = await self._proposals.get_in_hangout_for_update(
            hangout_id=hangout_id,
            proposal_id=proposal_id,
        )
        if proposal is None:
            raise ProposalNotFoundError
        return membership, hangout, proposal

    @staticmethod
    def _can_manage(
        *,
        current_user: User,
        membership: GroupMember,
        hangout: Hangout,
        proposal: Proposal,
    ) -> bool:
        return hangout.status == HangoutStatus.DRAFT and ProposalService._has_manage_permission(
            current_user=current_user,
            membership=membership,
            hangout=hangout,
            proposal=proposal,
        )

    @staticmethod
    def _has_manage_permission(
        *,
        current_user: User,
        membership: GroupMember,
        hangout: Hangout,
        proposal: Proposal,
    ) -> bool:
        return (
            proposal.submitted_by_user_id == current_user.id
            or hangout.created_by_user_id == current_user.id
            or membership.role == GroupMemberRole.OWNER
        )

    @classmethod
    def _require_manage_permission(
        cls,
        *,
        current_user: User,
        membership: GroupMember,
        hangout: Hangout,
        proposal: Proposal,
    ) -> None:
        if not cls._has_manage_permission(
            current_user=current_user,
            membership=membership,
            hangout=hangout,
            proposal=proposal,
        ):
            raise ProposalManageForbiddenError

    @staticmethod
    def _require_draft(hangout: Hangout) -> None:
        if hangout.status != HangoutStatus.DRAFT:
            raise ProposalStateConflictError

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _cursor_scope(*, group_id: UUID, hangout_id: UUID) -> str:
        return f"group:{group_id}:hangout:{hangout_id}"
