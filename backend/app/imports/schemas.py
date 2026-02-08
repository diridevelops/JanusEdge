"""Import validation schemas."""

from marshmallow import EXCLUDE, Schema, fields


class FinalizeTradeSchema(Schema):
    """Schema for a single trade in finalize request."""

    index = fields.Int(required=True)
    fee = fields.Float(load_default=0.0)


class FinalizeSchema(Schema):
    """Schema for the finalize import request."""

    class Meta:
        unknown = EXCLUDE

    file_hash = fields.Str(required=True)
    platform = fields.Str(required=True)
    file_name = fields.Str(required=True)
    reconstruction_method = fields.Str(
        load_default="FIFO"
    )
    trades = fields.List(
        fields.Nested(FinalizeTradeSchema),
        required=True,
    )
