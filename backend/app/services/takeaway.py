from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import InventoryItem, TakeawaySupply


def takeaway_supply_query():
    return select(TakeawaySupply).options(
        selectinload(TakeawaySupply.inventory_item).selectinload(
            InventoryItem.category
        )
    )


def list_takeaway_supplies(db: Session) -> list[TakeawaySupply]:
    return list(
        db.scalars(
            takeaway_supply_query().order_by(
                TakeawaySupply.created_at, TakeawaySupply.id
            )
        ).unique()
    )


def calculate_takeaway_requirements(
    db: Session, package_count: int
) -> tuple[dict[int, Decimal], list[TakeawaySupply]]:
    if package_count <= 0:
        return {}, []
    supplies = list_takeaway_supplies(db)
    multiplier = Decimal(package_count)
    return (
        {
            supply.inventory_item_id: Decimal(supply.quantity_per_package)
            * multiplier
            for supply in supplies
        },
        supplies,
    )


def merge_stock_requirements(
    *requirement_sets: dict[int, Decimal],
) -> dict[int, Decimal]:
    combined: dict[int, Decimal] = {}
    for requirements in requirement_sets:
        for item_id, quantity in requirements.items():
            combined[item_id] = combined.get(item_id, Decimal("0")) + quantity
    return combined
