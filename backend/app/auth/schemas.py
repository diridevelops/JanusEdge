"""Auth marshmallow schemas for validation."""

from marshmallow import Schema, fields, validate


class RegisterSchema(Schema):
    """Schema for user registration."""

    username = fields.Str(
        required=True,
        validate=validate.Length(min=3, max=50),
    )
    password = fields.Str(
        required=True,
        validate=validate.Length(min=6, max=128),
    )
    timezone = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=50),
    )


class LoginSchema(Schema):
    """Schema for user login."""

    username = fields.Str(required=True)
    password = fields.Str(required=True)


class ChangePasswordSchema(Schema):
    """Schema for password change."""

    current_password = fields.Str(required=True)
    new_password = fields.Str(
        required=True,
        validate=validate.Length(min=6, max=128),
    )


class UpdateTimezoneSchema(Schema):
    """Schema for timezone update."""

    timezone = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=50),
    )


class UpdateDisplayTimezoneSchema(Schema):
    """Schema for display timezone update."""

    display_timezone = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=50),
    )
