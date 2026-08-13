from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_vote_service
from app.core.exceptions import (
    DuplicateTimeVoteSelectionError,
    GroupNotFoundError,
    HangoutNotFoundError,
    ProposalNotFoundError,
    TimeOptionNotFoundError,
    VoteStateConflictError,
)
from app.main import app
from app.models.enums import HangoutStatus, ProposalVoteValue
from app.models.hangout import Hangout
from app.models.proposal import Proposal
from app.models.time_option import TimeOption
from app.models.user import User
from app.repositories.vote import ProposalVoteSummary, TimeVoteSummary
from app.services.vote import VotingSummary

NOW = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)


def make_user() -> User:
    return User(
        id=uuid4(),
        wechat_openid="openid-private",
        wechat_unionid="unionid-private",
        display_name="Member",
        avatar_url=None,
        is_active=True,
        profile_completed=True,
        last_login_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_resources(user: User, group_id):  # type: ignore[no-untyped-def]
    hangout = Hangout(
        id=uuid4(),
        group_id=group_id,
        created_by_user_id=user.id,
        title="Vote",
        description=None,
        status=HangoutStatus.VOTING,
        voting_deadline=NOW + timedelta(days=1),
        confirmed_at=None,
        cancelled_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    proposal = Proposal(
        id=uuid4(),
        hangout_id=hangout.id,
        submitted_by_user_id=user.id,
        title="Board games",
        description=None,
        location_text="Downtown",
        external_platform=None,
        external_url=None,
        external_data=None,
        created_at=NOW,
        updated_at=NOW,
    )
    time_option = TimeOption(
        id=uuid4(),
        hangout_id=hangout.id,
        created_by_user_id=user.id,
        starts_at=NOW + timedelta(days=2),
        ends_at=NOW + timedelta(days=2, hours=2),
        display_label="Friday",
        created_at=NOW,
        updated_at=NOW,
    )
    proposal_summary = ProposalVoteSummary(
        proposal=proposal,
        like_count=2,
        ok_count=1,
        dislike_count=0,
        current_user_vote=ProposalVoteValue.LIKE,
    )
    time_summary = TimeVoteSummary(
        time_option=time_option,
        availability_count=3,
        current_user_selected=True,
    )
    return hangout, proposal_summary, time_summary


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


async def request(method: str, path: str, **kwargs: object):  # type: ignore[no-untyped-def]
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


async def test_voting_summary_returns_counts_and_current_user_choices_in_envelope() -> None:
    user = make_user()
    group_id = uuid4()
    hangout, proposal, time_option = make_resources(user, group_id)

    class FakeService:
        async def read_summary(self, current_user: User, **arguments: object) -> VotingSummary:
            assert current_user is user
            assert arguments == {"group_id": group_id, "hangout_id": hangout.id}
            return VotingSummary(
                hangout=hangout,
                proposals=[proposal],
                time_options=[time_option],
            )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_vote_service] = FakeService

    response = await request(
        "GET",
        f"/api/v1/groups/{group_id}/hangouts/{hangout.id}/votes",
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "success",
        "data": {
            "hangout_id": str(hangout.id),
            "status": "voting",
            "voting_deadline": "2026-08-13T03:00:00Z",
            "proposals": [
                {
                    "id": str(proposal.proposal.id),
                    "submitted_by_user_id": str(user.id),
                    "title": "Board games",
                    "description": None,
                    "location_text": "Downtown",
                    "external_platform": None,
                    "external_url": None,
                    "external_data": None,
                    "created_at": "2026-08-12T03:00:00Z",
                    "updated_at": "2026-08-12T03:00:00Z",
                    "vote_counts": {"LIKE": 2, "OK": 1, "DISLIKE": 0},
                    "current_user_vote": "LIKE",
                }
            ],
            "time_options": [
                {
                    "id": str(time_option.time_option.id),
                    "created_by_user_id": str(user.id),
                    "starts_at": "2026-08-14T03:00:00Z",
                    "ends_at": "2026-08-14T05:00:00Z",
                    "display_label": "Friday",
                    "created_at": "2026-08-12T03:00:00Z",
                    "updated_at": "2026-08-12T03:00:00Z",
                    "availability_count": 3,
                    "current_user_selected": True,
                }
            ],
        },
    }


async def test_proposal_vote_put_and_delete_use_current_user_resource() -> None:
    user = make_user()
    group_id = uuid4()
    hangout, proposal, _time_option = make_resources(user, group_id)

    class FakeService:
        async def set_proposal_vote(
            self,
            current_user: User,
            **arguments: object,
        ) -> ProposalVoteSummary:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "hangout_id": hangout.id,
                "proposal_id": proposal.proposal.id,
                "value": ProposalVoteValue.DISLIKE,
            }
            return ProposalVoteSummary(
                proposal=proposal.proposal,
                like_count=1,
                ok_count=1,
                dislike_count=1,
                current_user_vote=ProposalVoteValue.DISLIKE,
            )

        async def delete_proposal_vote(
            self,
            current_user: User,
            **arguments: object,
        ) -> ProposalVoteSummary:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "hangout_id": hangout.id,
                "proposal_id": proposal.proposal.id,
            }
            return ProposalVoteSummary(
                proposal=proposal.proposal,
                like_count=1,
                ok_count=1,
                dislike_count=0,
                current_user_vote=None,
            )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_vote_service] = FakeService
    path = f"/api/v1/groups/{group_id}/hangouts/{hangout.id}/proposals/{proposal.proposal.id}/vote"

    put_response = await request("PUT", path, json={"value": "DISLIKE"})
    delete_response = await request("DELETE", path)

    assert put_response.status_code == 200
    assert put_response.json()["data"]["current_user_vote"] == "DISLIKE"
    assert put_response.json()["data"]["vote_counts"]["DISLIKE"] == 1
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["current_user_vote"] is None


async def test_time_vote_put_passes_only_option_ids_and_returns_updated_summary() -> None:
    user = make_user()
    group_id = uuid4()
    hangout, _proposal, time_option = make_resources(user, group_id)

    class FakeService:
        async def replace_time_votes(
            self,
            current_user: User,
            **arguments: object,
        ) -> list[TimeVoteSummary]:
            assert current_user is user
            assert arguments == {
                "group_id": group_id,
                "hangout_id": hangout.id,
                "time_option_ids": [time_option.time_option.id],
            }
            return [time_option]

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_vote_service] = FakeService

    response = await request(
        "PUT",
        f"/api/v1/groups/{group_id}/hangouts/{hangout.id}/time-votes/me",
        json={"time_option_ids": [str(time_option.time_option.id)]},
    )

    assert response.status_code == 200
    assert response.json()["data"]["time_options"][0]["current_user_selected"] is True


@pytest.mark.parametrize(
    ("path_suffix", "payload"),
    [
        (f"proposals/{uuid4()}/vote", {"value": "YES"}),
        (f"proposals/{uuid4()}/vote", {"value": "LIKE", "user_id": str(uuid4())}),
        ("time-votes/me", {"time_option_ids": [], "hangout_status": "voting"}),
    ],
)
async def test_vote_requests_reject_invalid_or_server_owned_fields(
    path_suffix: str,
    payload: dict[str, object],
) -> None:
    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vote_service] = lambda: object()

    response = await request(
        "PUT",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}/{path_suffix}",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json() == {"code": 40001, "message": "Invalid request", "data": None}


@pytest.mark.parametrize(
    ("error", "status_code", "code", "message"),
    [
        (GroupNotFoundError(), 404, 40410, "Group not found"),
        (HangoutNotFoundError(), 404, 40420, "Hangout not found"),
        (ProposalNotFoundError(), 404, 40430, "Proposal not found"),
        (TimeOptionNotFoundError(), 404, 40440, "Time option not found"),
        (VoteStateConflictError(), 409, 40950, "Hangout is not open for voting"),
        (
            DuplicateTimeVoteSelectionError(),
            422,
            42250,
            "Time option IDs must be unique",
        ),
    ],
)
async def test_vote_domain_errors_use_safe_envelope(
    error: Exception,
    status_code: int,
    code: int,
    message: str,
) -> None:
    class FakeService:
        async def replace_time_votes(self, *_args: object, **_kwargs: object) -> object:
            raise error

    app.dependency_overrides[get_current_user] = make_user
    app.dependency_overrides[get_vote_service] = FakeService

    response = await request(
        "PUT",
        f"/api/v1/groups/{uuid4()}/hangouts/{uuid4()}/time-votes/me",
        json={"time_option_ids": []},
    )

    assert response.status_code == status_code
    assert response.json() == {"code": code, "message": message, "data": None}
    assert "sql" not in response.text.lower()


def test_vote_routes_document_bearer_security_statuses_and_envelopes() -> None:
    schema = app.openapi()
    paths = [
        schema["paths"]["/api/v1/groups/{group_id}/hangouts/{hangout_id}/votes"]["get"],
        schema["paths"][
            "/api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals/{proposal_id}/vote"
        ]["put"],
        schema["paths"][
            "/api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals/{proposal_id}/vote"
        ]["delete"],
        schema["paths"]["/api/v1/groups/{group_id}/hangouts/{hangout_id}/time-votes/me"]["put"],
    ]

    for operation in paths:
        assert operation["security"] == [{"BearerAuth": []}]
        assert {"200", "401", "404", "409", "422"} <= set(operation["responses"])
        success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert success_schema["$ref"].startswith("#/components/schemas/ApiResponse_")
