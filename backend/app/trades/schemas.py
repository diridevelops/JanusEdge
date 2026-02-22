"""Trade validation schemas."""

from marshmallow import (
    Schema,
    fields,
    validate,
)


class ManualTradeSchema(Schema):
    """Schema for creating a manual trade."""

    symbol = fields.Str(required=True)
    side = fields.Str(
        required=True,
        validate=validate.OneOf(["Long", "Short"]),
    )
    total_quantity = fields.Int(required=True)
    entry_price = fields.Float(required=True)
    exit_price = fields.Float(required=True)
    entry_time = fields.DateTime(required=True)
    exit_time = fields.DateTime(required=True)
    fee = fields.Float(load_default=0.0)
    initial_risk = fields.Float(
        load_default=0.0,
        validate=validate.Range(min=0),
    )
    account = fields.Str(load_default="Manual")
    tags = fields.List(
        fields.Str(), load_default=[]
    )
    notes = fields.Str(load_default="")


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
