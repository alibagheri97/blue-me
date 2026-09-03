from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.db import get_db
from app.deps import client_ip, require_roles
from app.models import InventoryItem, TakeawaySupply, User, UserRole
from app.schemas import (
    TakeawaySupplyCreate,
    TakeawaySupplyRead,
    TakeawaySupplyUpdate,
)
from app.services.takeaway import list_takeaway_supplies, takeaway_supply_query

router = APIRouter(prefix="/takeaway-supplies", tags=["takeaway"])
takeaway_management_roles = require_roles(
    UserRole.ROOT, UserRole.ACCOUNTING_MANAGER
)


def serialize_supply(supply: TakeawaySupply) -> TakeawaySupplyRead:
    quantity = Decimal(supply.quantity_per_package)
    current_quantity = Decimal(supply.inventory_item.current_quantity)
    return TakeawaySupplyRead(
        id=supply.id,
        inventory_item_id=supply.inventory_item_id,
        quantity_per_package=quantity,
        calculated_cost=(
            quantity * Decimal(supply.inventory_item.average_cost)
        ).quantize(Decimal("0.01")),
        max_packages_available=max(0, int(current_quantity / quantity)),
        inventory_item=supply.inventory_item,
        created_at=supply.created_at,
        updated_at=supply.updated_at,
    )


def supply_or_404(db: Session, supply_id: int) -> TakeawaySupply:
    supply = db.scalar(takeaway_supply_query().where(TakeawaySupply.id == supply_id))
    if supply is None:
        raise HTTPException(status_code=404, detail="Takeaway supply not found")
    return supply


def available_inventory_or_422(db: Session, item_id: int) -> InventoryItem:
    item = db.get(InventoryItem, item_id)
    if item is None or not item.is_active:
        raise HTTPException(
            status_code=422, detail="Takeaway inventory item is unavailable"
        )
    return item


def ensure_unique_inventory(
    db: Session, item_id: int, *, exclude_id: int | None = None
) -> None:
    query = select(TakeawaySupply.id).where(
        TakeawaySupply.inventory_item_id == item_id
    )
    if exclude_id is not None:
        query = query.where(TakeawaySupply.id != exclude_id)
    if db.scalar(query) is not None:
        raise HTTPException(
            status_code=409,
            detail="This inventory item is already a takeaway supply",
        )


@router.get("", response_model=list[TakeawaySupplyRead])
def get_takeaway_supplies(
    _: User = Depends(takeaway_management_roles),
    db: Session = Depends(get_db),
) -> list[TakeawaySupplyRead]:
    return [serialize_supply(supply) for supply in list_takeaway_supplies(db)]


@router.post(
    "", response_model=TakeawaySupplyRead, status_code=status.HTTP_201_CREATED
)
def create_takeaway_supply(
    payload: TakeawaySupplyCreate,
    request: Request,
    actor: User = Depends(takeaway_management_roles),
    db: Session = Depends(get_db),
) -> TakeawaySupplyRead:
    item = available_inventory_or_422(db, payload.inventory_item_id)
    ensure_unique_inventory(db, item.id)
    supply = TakeawaySupply(
        inventory_item_id=item.id,
        quantity_per_package=payload.quantity_per_package,
        created_by_id=actor.id,
    )
    db.add(supply)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="menu",
        entity_type="takeaway_supply",
        entity_id=supply.id,
        summary=f"کالای بسته‌بندی بیرون‌بر {item.name} اضافه شد",
        details={
            "inventory_item_id": item.id,
            "inventory_item_name": item.name,
            "quantity_per_package": str(supply.quantity_per_package),
            "unit": item.unit,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    saved = supply_or_404(db, supply.id)
    return serialize_supply(saved)


@router.patch("/{supply_id}", response_model=TakeawaySupplyRead)
def update_takeaway_supply(
    supply_id: int,
    payload: TakeawaySupplyUpdate,
    request: Request,
    actor: User = Depends(takeaway_management_roles),
    db: Session = Depends(get_db),
) -> TakeawaySupplyRead:
    supply = supply_or_404(db, supply_id)
    before = {
        "inventory_item_id": supply.inventory_item_id,
        "inventory_item_name": supply.inventory_item.name,
        "quantity_per_package": str(supply.quantity_per_package),
        "unit": supply.inventory_item.unit,
    }
    if "inventory_item_id" in payload.model_fields_set:
        assert payload.inventory_item_id is not None
        item = available_inventory_or_422(db, payload.inventory_item_id)
        ensure_unique_inventory(db, item.id, exclude_id=supply.id)
        supply.inventory_item_id = item.id
        supply.inventory_item = item
    if "quantity_per_package" in payload.model_fields_set:
        assert payload.quantity_per_package is not None
        supply.quantity_per_package = payload.quantity_per_package
    db.flush()
    saved = supply_or_404(db, supply.id)
    record_audit(
        db,
        actor=actor,
        action="update",
        category="menu",
        entity_type="takeaway_supply",
        entity_id=supply.id,
        summary=f"کالای بسته‌بندی بیرون‌بر {saved.inventory_item.name} ویرایش شد",
        details={
            "before": before,
            "after": {
                "inventory_item_id": saved.inventory_item_id,
                "inventory_item_name": saved.inventory_item.name,
                "quantity_per_package": str(saved.quantity_per_package),
                "unit": saved.inventory_item.unit,
            },
        },
        ip_address=client_ip(request),
    )
    db.commit()
    return serialize_supply(supply_or_404(db, supply.id))


@router.delete("/{supply_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_takeaway_supply(
    supply_id: int,
    request: Request,
    actor: User = Depends(takeaway_management_roles),
    db: Session = Depends(get_db),
) -> None:
    supply = supply_or_404(db, supply_id)
    details = {
        "inventory_item_id": supply.inventory_item_id,
        "inventory_item_name": supply.inventory_item.name,
        "quantity_per_package": str(supply.quantity_per_package),
        "unit": supply.inventory_item.unit,
    }
    db.delete(supply)
    record_audit(
        db,
        actor=actor,
        action="delete",
        category="menu",
        entity_type="takeaway_supply",
        entity_id=supply.id,
        summary=f"کالای بسته‌بندی بیرون‌بر {details['inventory_item_name']} حذف شد",
        details=details,
        ip_address=client_ip(request),
    )
    db.commit()
