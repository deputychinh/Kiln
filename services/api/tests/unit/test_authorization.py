from datetime import UTC, datetime
from uuid import uuid4

import pytest

from kiln_api.domain.assets import Asset
from kiln_api.domain.authorization import authorize, visible_owner
from kiln_api.domain.identity import Principal
from kiln_api.enums import Action, AssetKind, AuthMethod, Scope
from kiln_api.errors import (
    InsufficientScopeError,
    NotCommentAuthorError,
    SessionRequiredError,
)

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


def _principal(method: AuthMethod, *scopes: Scope) -> Principal:
    return Principal(
        user_id=uuid4(),
        email="ada@kiln.test",
        display_name="Ada",
        method=method,
        scopes=frozenset(scopes),
    )


SESSION = _principal(AuthMethod.SESSION, Scope.READ, Scope.WRITE)
READ_TOKEN = _principal(AuthMethod.TOKEN, Scope.READ)
WRITE_TOKEN = _principal(AuthMethod.TOKEN, Scope.WRITE)
FULL_TOKEN = _principal(AuthMethod.TOKEN, Scope.READ, Scope.WRITE)


@pytest.mark.parametrize("action", [a for a in Action if a is not Action.CHANGE_OWN_COMMENT])
def test_a_browser_session_may_do_everything(action: Action) -> None:
    authorize(SESSION, action)


def test_the_required_scope_of_each_action_is_pinned() -> None:
    reads = {Action.READ_ASSETS, Action.READ_COMMENTS}
    writes = {
        Action.WRITE_ASSETS,
        Action.MANAGE_TOKENS,
        Action.WRITE_COMMENTS,
        Action.CHANGE_OWN_COMMENT,
    }

    assert reads | writes == set(Action)
    for action in reads:
        authorize(READ_TOKEN, action)
        with pytest.raises(InsufficientScopeError):
            authorize(WRITE_TOKEN, action)
    for action in writes - {Action.MANAGE_TOKENS}:
        authorize(WRITE_TOKEN, action, author_id=WRITE_TOKEN.user_id)
        with pytest.raises(InsufficientScopeError):
            authorize(READ_TOKEN, action, author_id=READ_TOKEN.user_id)


def test_only_the_author_may_change_a_comment() -> None:
    authorize(SESSION, Action.CHANGE_OWN_COMMENT, author_id=SESSION.user_id)

    with pytest.raises(NotCommentAuthorError):
        authorize(SESSION, Action.CHANGE_OWN_COMMENT, author_id=uuid4())


def test_changing_a_comment_without_naming_its_author_is_refused() -> None:
    """Deny by default: a use case that forgets the author is refused, never allowed."""
    with pytest.raises(NotCommentAuthorError):
        authorize(SESSION, Action.CHANGE_OWN_COMMENT)


def test_a_read_token_cannot_change_even_its_own_comment() -> None:
    with pytest.raises(InsufficientScopeError):
        authorize(READ_TOKEN, Action.CHANGE_OWN_COMMENT, author_id=READ_TOKEN.user_id)


def test_a_read_token_reads_but_cannot_write() -> None:
    authorize(READ_TOKEN, Action.READ_ASSETS)

    with pytest.raises(InsufficientScopeError):
        authorize(READ_TOKEN, Action.WRITE_ASSETS)


def test_a_write_only_token_cannot_read() -> None:
    authorize(WRITE_TOKEN, Action.WRITE_ASSETS)

    with pytest.raises(InsufficientScopeError):
        authorize(WRITE_TOKEN, Action.READ_ASSETS)


@pytest.mark.parametrize("token", [READ_TOKEN, FULL_TOKEN])
def test_no_token_may_manage_tokens_so_a_leaked_one_cannot_mint_more(token: Principal) -> None:
    with pytest.raises(SessionRequiredError):
        authorize(token, Action.MANAGE_TOKENS)


def test_the_single_workspace_lets_anyone_signed_in_reach_another_users_asset() -> None:
    """ADR 0012: v0.2 is one studio; the per-resource check is in place and passes."""
    asset = Asset(
        id=uuid4(),
        name="Rock",
        kind=AssetKind.IMAGE,
        created_at=NOW,
        updated_at=NOW,
        owner_id=uuid4(),
    )

    authorize(READ_TOKEN, Action.READ_ASSETS, asset)
    authorize(SESSION, Action.WRITE_ASSETS, asset)
    assert visible_owner(READ_TOKEN) is None


def test_the_scope_is_checked_before_the_resource() -> None:
    asset = Asset(id=uuid4(), name="Rock", kind=AssetKind.IMAGE, created_at=NOW, updated_at=NOW)

    with pytest.raises(InsufficientScopeError):
        authorize(READ_TOKEN, Action.WRITE_ASSETS, asset)
