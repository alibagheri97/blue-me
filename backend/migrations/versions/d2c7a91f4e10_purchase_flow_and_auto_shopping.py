"""purchase flow, menu catalog, historic costs, and automatic shopping

Revision ID: d2c7a91f4e10
Revises: b5da9da8aa00
Create Date: 2026-08-25 00:00:00
"""

from datetime import UTC, datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d2c7a91f4e10"
down_revision: Union[str, Sequence[str], None] = "b5da9da8aa00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "daily_needs",
        "status",
        existing_type=sa.String(length=8),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "price_change_requests",
        "status",
        existing_type=sa.String(length=8),
        type_=sa.String(length=20),
        existing_nullable=False,
    )

    op.add_column(
        "inventory_items",
        sa.Column(
            "target_stock_level",
            sa.Numeric(precision=14, scale=3),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "auto_reorder_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.create_index(
        op.f("ix_inventory_items_auto_reorder_enabled"),
        "inventory_items",
        ["auto_reorder_enabled"],
        unique=False,
    )

    op.create_table(
        "menu_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_menu_categories_created_at"), "menu_categories", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_menu_categories_is_active"), "menu_categories", ["is_active"], unique=False
    )

    op.add_column("menu_items", sa.Column("category_id", sa.Integer(), nullable=True))
    op.add_column("menu_items", sa.Column("inventory_item_id", sa.Integer(), nullable=True))
    op.add_column(
        "menu_items",
        sa.Column(
            "stock_quantity_per_sale",
            sa.Numeric(precision=14, scale=3),
            nullable=False,
            server_default="1",
        ),
    )
    op.create_foreign_key(
        "fk_menu_items_category_id", "menu_items", "menu_categories", ["category_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_menu_items_inventory_item_id",
        "menu_items",
        "inventory_items",
        ["inventory_item_id"],
        ["id"],
    )
    op.create_index(op.f("ix_menu_items_category_id"), "menu_items", ["category_id"], unique=False)
    op.create_index(
        op.f("ix_menu_items_inventory_item_id"),
        "menu_items",
        ["inventory_item_id"],
        unique=False,
    )

    connection = op.get_bind()
    category_names = [
        row[0]
        for row in connection.execute(
            sa.text("SELECT DISTINCT category FROM menu_items WHERE category IS NOT NULL AND category <> ''")
        )
    ]
    now = datetime.now(UTC).replace(tzinfo=None)
    menu_categories = sa.table(
        "menu_categories",
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("color", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    for index, name in enumerate(category_names):
        connection.execute(
            menu_categories.insert().values(
                name=name,
                description=None,
                color="#2563eb",
                sort_order=index,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
    for category_id, name in connection.execute(sa.text("SELECT id, name FROM menu_categories")):
        connection.execute(
            sa.text("UPDATE menu_items SET category_id = :category_id WHERE category = :name"),
            {"category_id": category_id, "name": name},
        )

    op.add_column(
        "order_items",
        sa.Column(
            "unit_cost",
            sa.Numeric(precision=16, scale=4),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "order_items",
        sa.Column(
            "line_cost",
            sa.Numeric(precision=16, scale=2),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "daily_needs",
        sa.Column(
            "source",
            sa.Enum("MANUAL", "AUTOMATIC", name="needsource", native_enum=False, length=20),
            nullable=False,
            server_default="MANUAL",
        ),
    )
    op.add_column(
        "daily_needs",
        sa.Column("quantity_at_creation", sa.Numeric(precision=14, scale=3), nullable=True),
    )
    op.add_column(
        "daily_needs",
        sa.Column("reorder_level_at_creation", sa.Numeric(precision=14, scale=3), nullable=True),
    )
    op.create_index(op.f("ix_daily_needs_source"), "daily_needs", ["source"], unique=False)

    op.create_table(
        "purchase_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_number", sa.String(length=40), nullable=False),
        sa.Column("supplier_name", sa.String(length=160), nullable=True),
        sa.Column("invoice_number", sa.String(length=100), nullable=True),
        sa.Column("purchased_at", sa.DateTime(), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("discount", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("extra_cost", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("total_cost", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("POSTED", "VOIDED", name="purchasestatus", native_enum=False, length=20),
            nullable=False,
            server_default="POSTED",
        ),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("voided_by_id", sa.Integer(), nullable=True),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["voided_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_purchase_receipt_date_status",
        "purchase_receipts",
        ["purchased_at", "status"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_receipt_supplier", "purchase_receipts", ["supplier_name"], unique=False
    )
    op.create_index(
        op.f("ix_purchase_receipts_created_at"),
        "purchase_receipts",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_receipts_invoice_number"),
        "purchase_receipts",
        ["invoice_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_receipts_purchased_at"),
        "purchase_receipts",
        ["purchased_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_receipts_receipt_number"),
        "purchase_receipts",
        ["receipt_number"],
        unique=True,
    )
    op.create_index(
        op.f("ix_purchase_receipts_status"), "purchase_receipts", ["status"], unique=False
    )

    op.create_table(
        "purchase_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(length=160), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("purchase_unit", sa.String(length=32), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("stock_quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("stock_unit", sa.String(length=32), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("allocated_cost", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("landed_total", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=16, scale=4), nullable=False),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
        sa.ForeignKeyConstraint(["receipt_id"], ["purchase_receipts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_purchase_line_item_receipt",
        "purchase_lines",
        ["inventory_item_id", "receipt_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_lines_inventory_item_id"),
        "purchase_lines",
        ["inventory_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_purchase_lines_receipt_id"), "purchase_lines", ["receipt_id"], unique=False
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_recipient_unread",
        "notifications",
        ["recipient_user_id", "is_read", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_created_at"), "notifications", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_notifications_is_read"), "notifications", ["is_read"], unique=False)
    op.create_index(op.f("ix_notifications_kind"), "notifications", ["kind"], unique=False)
    op.create_index(
        op.f("ix_notifications_recipient_user_id"),
        "notifications",
        ["recipient_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_recipient_user_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_kind"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_is_read"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_created_at"), table_name="notifications")
    op.drop_index("ix_notification_recipient_unread", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index(op.f("ix_purchase_lines_receipt_id"), table_name="purchase_lines")
    op.drop_index(op.f("ix_purchase_lines_inventory_item_id"), table_name="purchase_lines")
    op.drop_index("ix_purchase_line_item_receipt", table_name="purchase_lines")
    op.drop_table("purchase_lines")
    op.drop_index(op.f("ix_purchase_receipts_status"), table_name="purchase_receipts")
    op.drop_index(op.f("ix_purchase_receipts_receipt_number"), table_name="purchase_receipts")
    op.drop_index(op.f("ix_purchase_receipts_purchased_at"), table_name="purchase_receipts")
    op.drop_index(op.f("ix_purchase_receipts_invoice_number"), table_name="purchase_receipts")
    op.drop_index(op.f("ix_purchase_receipts_created_at"), table_name="purchase_receipts")
    op.drop_index("ix_purchase_receipt_supplier", table_name="purchase_receipts")
    op.drop_index("ix_purchase_receipt_date_status", table_name="purchase_receipts")
    op.drop_table("purchase_receipts")

    op.drop_index(op.f("ix_daily_needs_source"), table_name="daily_needs")
    op.drop_column("daily_needs", "reorder_level_at_creation")
    op.drop_column("daily_needs", "quantity_at_creation")
    op.drop_column("daily_needs", "source")
    op.drop_column("order_items", "line_cost")
    op.drop_column("order_items", "unit_cost")

    op.drop_index(op.f("ix_menu_items_inventory_item_id"), table_name="menu_items")
    op.drop_index(op.f("ix_menu_items_category_id"), table_name="menu_items")
    op.drop_constraint("fk_menu_items_inventory_item_id", "menu_items", type_="foreignkey")
    op.drop_constraint("fk_menu_items_category_id", "menu_items", type_="foreignkey")
    op.drop_column("menu_items", "stock_quantity_per_sale")
    op.drop_column("menu_items", "inventory_item_id")
    op.drop_column("menu_items", "category_id")
    op.drop_index(op.f("ix_menu_categories_is_active"), table_name="menu_categories")
    op.drop_index(op.f("ix_menu_categories_created_at"), table_name="menu_categories")
    op.drop_table("menu_categories")

    op.drop_index(op.f("ix_inventory_items_auto_reorder_enabled"), table_name="inventory_items")
    op.drop_column("inventory_items", "auto_reorder_enabled")
    op.drop_column("inventory_items", "target_stock_level")
    op.alter_column(
        "price_change_requests",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=8),
        existing_nullable=False,
    )
    op.alter_column(
        "daily_needs",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=8),
        existing_nullable=False,
    )
