"""Trade validation schemas."""

from marshmallow import (
    Schema,
    ValidationError,
    fields,
    validate,
)
from marshmallow.decorators import validates_schema


class ManualTradeSchema(Schema):
    """Schema for creating a manual trade."""

    symbol = fields.Str(required=True)
    side = fields.Str(
        required=True,
        validate=validate.OneOf(["Long", "Short"]),
    )
    total_quantity = fields.Int(
        required=False,
        allow_none=True,
        validate=validate.Range(min=1),
    )
    lot_size = fields.Float(
        required=False,
        allow_none=True,
        validate=validate.Range(min=0.001),
    )
    entry_price = fields.Float(required=True)
    exit_price = fields.Float(required=True)
    entry_time = fields.DateTime(required=True)
    exit_time = fields.DateTime(required=True)
    fee = fields.Float(load_default=0.0)
    quote_to_usd_rate = fields.Float(
        required=False,
        allow_none=True,
        validate=validate.Range(min=0, min_inclusive=False),
    )
    initial_risk = fields.Float(
        load_default=0.0,
        validate=validate.Range(min=0),
    )
    account = fields.Str(load_default="Manual")
    tags = fields.List(
        fields.Str(), load_default=[]
    )
    notes = fields.Str(load_default="")

    @validates_schema
    def validate_quantity_fields(self, data, **kwargs) -> None:
        """Require a quantity for either futures or forex entry."""
        if data.get("total_quantity") is None and data.get("lot_size") is None:
            raise ValidationError(
                "Either total_quantity or lot_size is required."
            )


class UpdateTradeSchema(Schema):
    """Schema for updating a trade."""

    fee = fields.Float()
    initial_risk = fields.Float(
        validate=validate.Range(min=0)
    )
    fee_source = fields.Str()
    strategy = fields.Str(allow_none=True)
    pre_trade_notes = fields.Str(allow_none=True)
    post_trade_notes = fields.Str(allow_none=True)
    tag_ids = fields.List(fields.Str())
    wish_stop_price = fields.Float(allow_none=True)
    target_price = fields.Float(allow_none=True)
