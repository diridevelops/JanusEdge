"""Auth marshmallow schemas for validation."""

from marshmallow import Schema, ValidationError, fields, validate
from marshmallow.decorators import validates_schema

from app.market_data.symbol_mapper import (
    validate_market_data_mappings,
    validate_symbol_mappings,
)


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


class UpdateStartingEquitySchema(Schema):
    """Schema for starting equity update."""

    starting_equity = fields.Float(
        required=True,
        validate=validate.Range(min=0),
    )


class UpdateWhatIfTargetRMultipleSchema(Schema):
    """Schema for the default What-if target R-multiple."""

    whatif_target_r_multiple = fields.Float(
        required=True,
        validate=validate.Range(min=0, min_inclusive=False),
    )


class BaseSymbolMappingSchema(Schema):
    """Schema for a single base symbol mapping entry."""

    dollar_value_per_point = fields.Float(
        required=True,
        validate=validate.Range(min=0, min_inclusive=False),
    )


class UpdateSymbolMappingsSchema(Schema):
    """Schema for symbol mappings update."""

    symbol_mappings = fields.Dict(
        keys=fields.Str(
            validate=validate.Length(min=1, max=32)
        ),
        values=fields.Nested(BaseSymbolMappingSchema()),
        required=True,
    )

    @validates_schema
    def validate_entries(self, data, **kwargs) -> None:
        """Run centralized symbol mapping validation."""
        try:
            validate_symbol_mappings(
                data["symbol_mappings"]
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class UpdateMarketDataMappingsSchema(Schema):
    """Schema for market-data mappings update."""

    market_data_mappings = fields.Dict(
        keys=fields.Str(
            validate=validate.Length(min=1, max=32)
        ),
        values=fields.Str(
            validate=validate.Length(min=1, max=32)
        ),
        required=True,
    )

    @validates_schema
    def validate_entries(self, data, **kwargs) -> None:
        """Run centralized market-data mapping validation."""
        try:
            validate_market_data_mappings(
                data["market_data_mappings"]
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class RestoreArchiveSchema(Schema):
    """Schema for restore archive upload metadata."""

    filename = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=255),
    )


class BackupManifestSchema(Schema):
    """Schema for portable backup archive manifests."""

    archive_type = fields.Str(
        required=True,
        validate=validate.OneOf(
            ["janusedge-portable-backup"]
        ),
    )
    version = fields.Str(
        required=True,
        validate=validate.OneOf(["1.0"]),
    )
    created_at = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=64),
    )
    counts = fields.Dict(
        keys=fields.Str(),
        values=fields.Int(validate=validate.Range(min=0)),
        required=True,
    )
