"""Authentication service — business logic."""

import bcrypt
from flask_jwt_extended import create_access_token

from app.models.user import create_user_doc
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

    def register(
        self,
        username: str,
        password: str,
        timezone: str,
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
        )
        user_id = self.user_repo.insert_one(user_doc)

        token = create_access_token(identity=user_id)

        return {
            "token": token,
            "user": {
                "id": user_id,
                "username": username,
                "timezone": timezone,
                "display_timezone": timezone,
            },
        }

    def login(
        self, username: str, password: str
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

        return {
            "token": token,
            "user": {
                "id": user_id,
                "username": user["username"],
                "timezone": user["timezone"],
                "display_timezone": user.get(
                    "display_timezone",
                    user["timezone"],
                ),
            },
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

        return {
            "id": str(user["_id"]),
            "username": user["username"],
            "timezone": user["timezone"],
            "display_timezone": user.get(
                "display_timezone",
                user["timezone"],
            ),
        }

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
        return {"message": "Password changed successfully."}

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

        return {
            "id": str(user["_id"]),
            "username": user["username"],
            "timezone": timezone,
            "display_timezone": user.get(
                "display_timezone",
                timezone,
            ),
        }

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

        return {
            "id": str(user["_id"]),
            "username": user["username"],
            "timezone": user["timezone"],
            "display_timezone": display_timezone,
        }
