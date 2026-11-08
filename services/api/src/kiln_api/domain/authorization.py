"""The one authorization policy (ADR 0012): every route and service asks it, nothing else decides.

v0.2 is a single workspace: every signed-in user sees and changes every asset, so the per-resource
check below always passes. Multi-tenancy later changes `_in_workspace` (and the list filter in
`visible_owner`) and nothing else.
"""

from uuid import UUID

from kiln_api.domain.assets import Asset
from kiln_api.domain.identity import Principal
from kiln_api.enums import Action, AuthMethod, Scope
from kiln_api.errors import (
    AssetNotFoundError,
    InsufficientScopeError,
    NotCommentAuthorError,
    SessionRequiredError,
)

_REQUIRED_SCOPE: dict[Action, Scope] = {
    Action.READ_ASSETS: Scope.READ,
    Action.WRITE_ASSETS: Scope.WRITE,
    Action.MANAGE_TOKENS: Scope.WRITE,
    # Comments (KILN-10): whoever can read an asset may comment on it (one studio, ADR 0012).
    Action.READ_COMMENTS: Scope.READ,
    Action.WRITE_COMMENTS: Scope.WRITE,
    Action.CHANGE_OWN_COMMENT: Scope.WRITE,
    # Reviews (KILN-11): in one studio any writer may approve, request changes or reopen, their
    # own uploads included (ADR 0015); required reviewers and approval chains come later.
    Action.READ_REVIEWS: Scope.READ,
    Action.REVIEW_VERSIONS: Scope.WRITE,
}
_SESSION_ONLY = frozenset({Action.MANAGE_TOKENS})
# Actions on something one person wrote: only that person, whatever the workspace allows.
_AUTHOR_ONLY = frozenset({Action.CHANGE_OWN_COMMENT})


def authorize(
    principal: Principal,
    action: Action,
    asset: Asset | None = None,
    *,
    author_id: UUID | None = None,
) -> None:
    """Allow `action` (on `asset`, and on something written by `author_id`, when given) or raise.

    Author-only actions are refused unless `author_id` is the caller (deny by default: a call that
    forgets to pass the author is refused, never allowed).

    Raises:
        SessionRequiredError: The action needs a browser session (a leaked token cannot mint more).
        InsufficientScopeError: The token lacks the scope (403, BOLA/BFLA guard).
        AssetNotFoundError: The asset is outside the caller's workspace (404, so ids do not leak).
        NotCommentAuthorError: The action is the author's alone (403).
    """
    if action in _SESSION_ONLY and principal.method is not AuthMethod.SESSION:
        raise SessionRequiredError
    if _REQUIRED_SCOPE[action] not in principal.scopes:
        raise InsufficientScopeError
    if asset is not None and not _in_workspace(principal, asset):
        raise AssetNotFoundError(asset.id)
    if action in _AUTHOR_ONLY and author_id != principal.user_id:
        raise NotCommentAuthorError


def visible_owner(principal: Principal) -> UUID | None:
    """The owner a listing is limited to; None means the whole (single) workspace."""
    return None if _single_workspace(principal) else principal.user_id


def _in_workspace(principal: Principal, asset: Asset) -> bool:
    return _single_workspace(principal) or asset.owner_id == principal.user_id


def _single_workspace(_principal: Principal) -> bool:
    return True  # v0.2: one studio per deployment (ADR 0012)
