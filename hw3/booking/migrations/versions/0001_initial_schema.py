import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("flight_id", sa.Uuid(), nullable=False),
        sa.Column("passenger_name", sa.String(length=255), nullable=False),
        sa.Column("passenger_email", sa.String(length=254), nullable=False),
        sa.Column("seat_count", sa.Integer(), nullable=False),
        sa.Column("total_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("CONFIRMED", "CANCELLED", name="booking_status"),
            server_default="CONFIRMED",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "total_price > 0 AND total_price <> 'NaN'::numeric",
            name="ck_bookings_total_price",
        ),
        sa.CheckConstraint(
            "length(btrim(passenger_email)) > 0", name="ck_bookings_passenger_email"
        ),
        sa.CheckConstraint(
            "length(btrim(passenger_name)) > 0", name="ck_bookings_passenger_name"
        ),
        sa.CheckConstraint("seat_count > 0", name="ck_bookings_seat_count"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bookings_user", "bookings", ["user_id", "created_at", "id"], unique=False
    )


def downgrade():
    op.drop_index("ix_bookings_user", table_name="bookings")
    op.drop_table("bookings")
    sa.Enum(name="booking_status").drop(op.get_bind(), checkfirst=True)
