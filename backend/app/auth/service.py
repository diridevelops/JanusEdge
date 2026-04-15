"""Authentication service — business logic."""

import bcrypt
import hashlib
import secrets
from flask_jwt_extended import create_access_token

from app.auth.backup_service import PortableBackupService
from app.market_data.symbol_mapper import (
    get_effective_market_data_mappings,
    get_effective_symbol_mappings,
    get_default_market_data_mappings,
    get_default_symbol_mappings,
    validate_market_data_mappings,
)
from app.models.auth_refresh_session import (
    create_auth_refresh_session_doc,
)
from app.models.user import (
    DEFAULT_STARTING_EQUITY,
    DEFAULT_WHATIF_TARGET_R_MULTIPLE,
    create_user_doc,
)
from app.repositories.auth_refresh_session_repo import (
    AuthRefreshSessionRepository,
)
from app.repositories.user_repo import UserRepository
from app.utils.errors import (
    AuthenticationError,
    ValidationError,
)
from app.utils.validators import is_valid_timezone


class AuthService:
    """Service for authentication operations."""

    def __init__(self):
        self.user_repo = UserRepository()
        self.refresh_session_repo = (
            AuthRefreshSessionRepository()
        )
        self.backup_service = PortableBackupService()

    def register(
        self,
        username: str,
        password: str,
        timezone: str,
        user_agent: str | None = None,
    ) -> dict:
        """
        Register a new user.

        Parameters:
            username: Desired username.
            password: Plain-text password.
            timezone: User's trading timezone.

        Returns:
            Dict with token and user profile.

        Raises:
            ValidationError: If username taken or invalid tz.
        """
        if not is_valid_timezone(timezone):
            raise ValidationError(
                f"Invalid timezone: {timezone}"
            )

        existing = self.user_repo.find_by_username(username)
        if existing:
            raise ValidationError(
                "Username already exists."
            )

        password_hash = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=12),
        ).decode("utf-8")

        user_doc = create_user_doc(
            username=username,
            password_hash=password_hash,
            timezone=timezone,
            symbol_mappings=get_default_symbol_mappings(),
            market_data_mappings=get_default_market_data_mappings(),
        )
        user_id = self.user_repo.insert_one(user_doc)

        token = create_access_token(identity=user_id)
        refresh_token = self._create_refresh_session(
            user_id=user_id,
            user_agent=user_agent,
        )
        user_doc["_id"] = user_id

        return {
            "token": token,
            "user": self._serialize_user_profile(user_doc),
            "refresh_token": refresh_token,
        }

    def login(
        self,
        username: str,
        password: str,
        user_agent: str | None = None,
    ) -> dict:
        """
        Authenticate a user and return a token.

        Parameters:
            username: The username.
            password: Plain-text password.

        Returns:
            Dict with token and user profile.

        Raises:
            AuthenticationError: If credentials invalid.
        """
        user = self.user_repo.find_by_username(username)
        if not user:
            raise AuthenticationError(
                "Invalid username or password."
            )

        if not bcrypt.checkpw(
            password.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        ):
            raise AuthenticationError(
                "Invalid username or password."
            )

        user_id = str(user["_id"])
        token = create_access_token(identity=user_id)
        refresh_token = self._create_refresh_session(
            user_id=user_id,
            user_agent=user_agent,
        )

        return {
            "token": token,
            "user": self._serialize_user_profile(user),
            "refresh_token": refresh_token,
        }

    def refresh_session(
        self,
        refresh_token: str,
    ) -> dict:
        """Rotate a refresh session and issue a new access token."""

        session = self.refresh_session_repo.find_active_by_token_hash(
            self._hash_refresh_token(refresh_token)
        )
        if not session:
            raise AuthenticationError(
                "Session expired. Please log in again."
            )

        user_id = str(session["user_id"])
        user = self.user_repo.find_by_id(user_id)
        if not user:
            self.refresh_session_repo.revoke_by_token_hash(
                session["token_hash"]
            )
            raise AuthenticationError(
                "Session expired. Please log in again."
            )

        next_refresh_token = self._generate_refresh_token()
        next_refresh_token_hash = self._hash_refresh_token(
            next_refresh_token
        )
        self.refresh_session_repo.rotate_session(
            str(session["_id"]),
            token_hash=next_refresh_token_hash,
        )

        return {
            "token": create_access_token(identity=user_id),
            "user": self._serialize_user_profile(user),
            "refresh_token": next_refresh_token,
        }

    def get_profile(self, user_id: str) -> dict:
        """
        Get user profile by ID.

        Parameters:
            user_id: The user's ObjectId string.

        Returns:
            User profile dict.

        Raises:
            AuthenticationError: If user not found.
        """
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found.")

        return self._serialize_user_profile(user)

    def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> dict:
        """
        Change a user's password.

        Parameters:
            user_id: The user's ObjectId string.
            current_password: Current plain-text password.
            new_password: New plain-text password.

        Returns:
            Success message dict.

        Raises:
            AuthenticationError: If user not found
                or current password wrong.
        """
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found.")

        if not bcrypt.checkpw(
            current_password.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        ):
            raise AuthenticationError(
                "Current password is incorrect."
            )

        new_hash = bcrypt.hashpw(
            new_password.encode("utf-8"),
            bcrypt.gensalt(rounds=12),
        ).decode("utf-8")

        self.user_repo.update_password(user_id, new_hash)
        self.refresh_session_repo.revoke_all_for_user(
            user_id
        )
        return {"message": "Password changed successfully."}

    def logout(
        self,
        refresh_token: str | None,
    ) -> dict:
        """Revoke the current browser refresh session."""

        if refresh_token:
            self.refresh_session_repo.revoke_by_token_hash(
                self._hash_refresh_token(refresh_token)
            )
        return {"message": "Logged out."}

    def update_timezone(
        self,
        user_id: str,
        timezone: str,
    ) -> dict:
        """
        Update a user's trading timezone.

        Parameters:
            user_id: The user's ObjectId string.
            timezone: New timezone string.

        Returns:
            Updated user profile dict.

        Raises:
            AuthenticationError: If user not found.
            ValidationError: If timezone invalid.
        """
        if not is_valid_timezone(timezone):
            raise ValidationError(
                f"Invalid timezone: {timezone}"
            )

        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found.")

        self.user_repo.update_timezone(user_id, timezone)
        updated_user = dict(user)
        updated_user["timezone"] = timezone
        return self._serialize_user_profile(updated_user)

    def update_display_timezone(
        self,
        user_id: str,
        display_timezone: str,
    ) -> dict:
        """
        Update a user's display timezone.

        Parameters:
            user_id: The user's ObjectId string.
            display_timezone: New display timezone.

        Returns:
            Updated user profile dict.

        Raises:
            AuthenticationError: If user not found.
            ValidationError: If timezone invalid.
        """
        if not is_valid_timezone(display_timezone):
            raise ValidationError(
                f"Invalid timezone: {display_timezone}"
            )

        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found.")

        self.user_repo.update_display_timezone(
            user_id, display_timezone
        )
        updated_user = dict(user)
        updated_user["display_timezone"] = display_timezone
        return self._serialize_user_profile(updated_user)

    def update_starting_equity(
        self,
        user_id: str,
        starting_equity: float,
    ) -> dict:
        """
        Update a user's starting equity for simulations.

        Parameters:
            user_id: The user's ObjectId string.
            starting_equity: New starting equity value.

        Returns:
            Updated user profile dict.

        Raises:
            AuthenticationError: If user not found.
        """
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found.")

        self.user_repo.update_starting_equity(
            user_id, starting_equity
        )
        updated_user = dict(user)
        updated_user["starting_equity"] = starting_equity
        return self._serialize_user_profile(updated_user)

    def update_whatif_target_r_multiple(
        self,
        user_id: str,
        whatif_target_r_multiple: float,
    ) -> dict:
        """
        Update a user's default What-if target R-multiple.

        Parameters:
            user_id: The user's ObjectId string.
            whatif_target_r_multiple: New target R-multiple.

        Returns:
            Updated user profile dict.

        Raises:
            AuthenticationError: If user not found.
        """
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found.")

        self.user_repo.update_whatif_target_r_multiple(
            user_id,
            whatif_target_r_multiple,
        )
        updated_user = dict(user)
        updated_user["whatif_target_r_multiple"] = (
            whatif_target_r_multiple
        )
        return self._serialize_user_profile(updated_user)

    def update_symbol_mappings(
        self,
        user_id: str,
        symbol_mappings: dict,
    ) -> dict:
        """
        Update a user's symbol mappings.

        Parameters:
            user_id: The user's ObjectId string.
            symbol_mappings: Replacement mapping configuration.

        Returns:
            Updated user profile dict.

        Raises:
            AuthenticationError: If user not found.
            ValidationError: If mappings are invalid.
        """
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found.")

        try:
            normalized_mappings = get_effective_symbol_mappings(
                symbol_mappings
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        self.user_repo.update_symbol_mappings(
            user_id,
            normalized_mappings,
        )

        updated_user = dict(user)
        updated_user["symbol_mappings"] = normalized_mappings
        return self._serialize_user_profile(updated_user)

    def update_market_data_mappings(
        self,
        user_id: str,
        market_data_mappings: dict,
    ) -> dict:
        """
        Update a user's market-data mappings.

        Parameters:
            user_id: The user's ObjectId string.
            market_data_mappings: Replacement mapping configuration.

        Returns:
            Updated user profile dict.

        Raises:
            AuthenticationError: If user not found.
            ValidationError: If mappings are invalid.
        """
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found.")

        try:
            normalized_mappings = (
                validate_market_data_mappings(
                    market_data_mappings
                )
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        self.user_repo.update_market_data_mappings(
            user_id,
            normalized_mappings,
        )

        updated_user = dict(user)
        updated_user["market_data_mappings"] = (
            normalized_mappings
        )
        return self._serialize_user_profile(updated_user)

    def export_backup(
        self, user_id: str
    ) -> tuple[object, str]:
        """Create a portable backup archive for a user."""
        return self.backup_service.export_backup(user_id)

    def restore_backup(
        self, user_id: str, archive_file
    ) -> dict:
        """Restore a portable backup archive into a user."""
        return self.backup_service.restore_backup(
            user_id, archive_file
        )

    def _serialize_user_profile(
        self, user: dict
    ) -> dict:
        """Serialize a user document for auth/profile responses."""
        return {
            "id": str(user["_id"]),
            "username": user["username"],
            "timezone": user["timezone"],
            "display_timezone": user.get(
                "display_timezone",
                user["timezone"],
            ),
            "starting_equity": user.get(
                "starting_equity", DEFAULT_STARTING_EQUITY
            ),
            "whatif_target_r_multiple": user.get(
                "whatif_target_r_multiple",
                DEFAULT_WHATIF_TARGET_R_MULTIPLE,
            ),
            "symbol_mappings": get_effective_symbol_mappings(
                user.get("symbol_mappings")
            ),
            "market_data_mappings": (
                get_effective_market_data_mappings(
                    user.get("market_data_mappings")
                )
            ),
        }

    def _create_refresh_session(
        self,
        *,
        user_id: str,
        user_agent: str | None,
    ) -> str:
        """Create and persist one refresh session."""

        refresh_token = self._generate_refresh_token()
        session_doc = create_auth_refresh_session_doc(
            user_id=user_id,
            token_hash=self._hash_refresh_token(
                refresh_token
            ),
            user_agent=user_agent,
        )
        self.refresh_session_repo.insert_one(session_doc)
        return refresh_token

    @staticmethod
    def _generate_refresh_token() -> str:
        """Generate a new opaque refresh token."""

        return secrets.token_urlsafe(64)

    @staticmethod
    def _hash_refresh_token(refresh_token: str) -> str:
        """Hash a refresh token before storing or lookup."""

        return hashlib.sha256(
            refresh_token.encode("utf-8")
        ).hexdigest()
