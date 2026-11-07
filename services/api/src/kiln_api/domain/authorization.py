"""The one authorization policy (ADR 0012): every route and service asks it, nothing else decides.

v0.2 is a single workspace: every signed-in user sees and changes every asset, so the per-resource
check below always passes. Multi-tenancy later changes `_in_workspace` (and the list filter in
`visible_owner`) and nothing else.
"""

from uuid import UUID

from kiln_api.domain.assets import Asset
from kiln_api.domain.identity import Principal
from kiln_api.enums import Action, AuthMethod, Scope
from kiln_api.errors import AssetNotFoundError, InsufficientScopeError, SessionRequiredError

_REQUIRED_SCOPE: dict[Action, Scope] = {
    Action.READ_ASSETS: Scope.READ,
    Action.WRITE_ASSETS: Scope.WRITE,
    Action.MANAGE_TOKENS: Scope.WRITE,
}
_SESSION_ONLY = frozenset({Action.MANAGE_TOKENS})


def authorize(principal: Principal, action: Action, asset: Asset | None = None) -> None:
    """Allow `action` (on `asset`, when given) or raise.

    Raises:
        SessionRequiredError: The action needs a browser session (a leaked token cannot mint more).
        InsufficientScopeError: The token lacks the scope (403, BOLA/BFLA guard).
        AssetNotFoundError: The asset is outside the caller's workspace (404, so ids do not leak).
    """
    if action in _SESSION_ONLY and principal.method is not AuthMethod.SESSION:
        raise SessionRequiredError
    if _REQUIRED_SCOPE[action] not in principal.scopes:
        raise InsufficientScopeError
    if asset is not None and not _in_workspace(principal, asset):
        raise AssetNotFoundError(asset.id)


def visible_owner(principal: Principal) -> UUID | None:
    """The owner a listing is limited to; None means the whole (single) workspace."""
    return None if _single_workspace(principal) else principal.user_id


def _in_workspace(principal: Principal, asset: Asset) -> bool:
    return _single_workspace(principal) or asset.owner_id == principal.user_id


def _single_workspace(_principal: Principal) -> bool:
    return True  # v0.2: one studio per deployment (ADR 0012)
