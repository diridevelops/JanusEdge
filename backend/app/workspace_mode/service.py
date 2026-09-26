"""Workspace-mode lookup, validation, and write guards."""

from bson import ObjectId

from app.repositories.account_repo import AccountRepository
from app.utils.errors import ForbiddenError, ValidationError
from app.workspace_mode.repository import WorkspaceModeRepository


WORKSPACE_MODES = frozenset({"real", "backtest"})


class WorkspaceModeService:
    """Resolve and persist the mode belonging to an authenticated user."""

    def __init__(self, repository=None):
        self.repository = repository or WorkspaceModeRepository()

    def get_active_mode(self, user_id: str) -> str:
        """Return the saved mode, defaulting legacy users to Real."""
        document = self.repository.find_by_user(user_id)
        active_mode = document.get("active_mode") if document else None
        return active_mode if active_mode in WORKSPACE_MODES else "real"

    def set_active_mode(self, user_id: str, active_mode) -> str:
        """Validate and save one supported workspace mode."""
        if not isinstance(active_mode, str) or active_mode not in WORKSPACE_MODES:
            raise ValidationError(
                "active_mode must be either 'real' or 'backtest'."
            )
        self.repository.save_for_user(user_id, active_mode)
        return active_mode


def get_active_workspace_mode(user_id: str) -> str:
    """Return the authenticated user's active mode."""
    return WorkspaceModeService().get_active_mode(user_id)


def get_workspace_account_ids(
    user_id: str, active_mode: str | None = None
) -> list[ObjectId]:
    """Return account ids visible in the requested/current workspace."""
    mode = active_mode or get_active_workspace_mode(user_id)
    accounts = AccountRepository().find_by_user(
        user_id, workspace_mode=mode
    )
    return [account["_id"] for account in accounts]


def require_real_workspace(user_id: str) -> None:
    """Reject Real trade-import or manual-entry actions in Backtest mode."""
    if get_active_workspace_mode(user_id) != "real":
        raise ForbiddenError(
            "This action is unavailable in Backtest workspace mode."
        )
