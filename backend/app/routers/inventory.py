from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit
from app.core.config import settings
from app.db import get_db
from app.deps import client_ip, require_roles
from app.models import (
    ApprovalStatus,
    Category,
    InventoryItem,
    MovementType,
    PriceChangeRequest,
    StockMovement,
    User,
    UserRole,
)
from app.schemas import (
    ApprovalDecision,
    CategoryCreate,
    CategoryRead,
    InventoryItemCreate,
    InventoryItemRead,
    InventoryItemUpdate,
    MovementCreate,
    MovementRead,
    PaginatedItems,
    PriceRequestCreate,
    PriceRequestRead,
)
from app.services.inventory_alerts import sync_auto_purchase_need

router = APIRouter(prefix="/inventory", tags=["inventory"])
inventory_roles = require_roles(UserRole.ROOT, UserRole.STORAGE_MANAGER)
all_staff = require_roles(*list(UserRole))
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def get_item_or_404(db: Session, item_id: int, *, lock: bool = False) -> InventoryItem:
    query = select(InventoryItem).where(InventoryItem.id == item_id)
    if lock:
        query = query.with_for_update()
    item = db.scalar(query)
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return item


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(_: User = Depends(all_staff), db: Session = Depends(get_db)) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.name)))


@router.post("/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    request: Request,
    actor: User = Depends(inventory_roles),
    db: Session = Depends(get_db),
) -> Category:
    if db.scalar(select(Category.id).where(func.lower(Category.name) == payload.name.lower())):
        raise HTTPException(status_code=409, detail="Category already exists")
    category = Category(**payload.model_dump())
    db.add(category)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="inventory",
        entity_type="category",
        entity_id=category.id,
        summary=f"Created inventory category {category.name}",
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(category)
    return category


@router.patch("/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    payload: CategoryCreate,
    request: Request,
    actor: User = Depends(inventory_roles),
    db: Session = Depends(get_db),
) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    duplicate = db.scalar(
        select(Category.id).where(func.lower(Category.name) == payload.name.lower(), Category.id != category_id)
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Category name already exists")
    for key, value in payload.model_dump().items():
        setattr(category, key, value)
    record_audit(
        db,
        actor=actor,
        action="update",
        category="inventory",
        entity_type="category",
        entity_id=category.id,
        summary=f"Updated inventory category {category.name}",
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    request: Request,
    actor: User = Depends(inventory_roles),
    db: Session = Depends(get_db),
) -> None:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if db.scalar(select(func.count()).select_from(InventoryItem).where(InventoryItem.category_id == category_id)):
        raise HTTPException(status_code=409, detail="Move the items in this category before deleting it")
    record_audit(
        db,
        actor=actor,
        action="delete",
        category="inventory",
        entity_type="category",
        entity_id=category.id,
        summary=f"Deleted inventory category {category.name}",
        ip_address=client_ip(request),
    )
    db.delete(category)
    db.commit()


@router.get("/items", response_model=PaginatedItems)
def list_items(
    search: str | None = Query(default=None, max_length=160),
    category_id: int | None = None,
    low_stock: bool = False,
    active: bool | None = True,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    _: User = Depends(all_staff),
    db: Session = Depends(get_db),
) -> PaginatedItems:
    filters = []
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(InventoryItem.name.ilike(term), InventoryItem.sku.ilike(term)))
    if category_id is not None:
        filters.append(InventoryItem.category_id == category_id)
    if low_stock:
        filters.append(InventoryItem.current_quantity <= InventoryItem.reorder_level)
    if active is not None:
        filters.append(InventoryItem.is_active == active)
    total = db.scalar(select(func.count()).select_from(InventoryItem).where(*filters)) or 0
    query = (
        select(InventoryItem)
        .options(selectinload(InventoryItem.category))
        .where(*filters)
        .order_by(InventoryItem.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return PaginatedItems(items=list(db.scalars(query)), total=total, page=page, page_size=page_size)


@router.post("/items", response_model=InventoryItemRead, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: InventoryItemCreate,
    request: Request,
    actor: User = Depends(inventory_roles),
    db: Session = Depends(get_db),
) -> InventoryItem:
    if db.scalar(select(InventoryItem.id).where(InventoryItem.sku == payload.sku)):
        raise HTTPException(status_code=409, detail="SKU already exists")
    if payload.category_id is not None and db.get(Category, payload.category_id) is None:
        raise HTTPException(status_code=400, detail="Category does not exist")
    data = payload.model_dump()
    requested_price = data.pop("selling_price")
    item = InventoryItem(**data, selling_price=requested_price if actor.role == UserRole.ROOT else 0)
    db.add(item)
    db.flush()
    if actor.role == UserRole.STORAGE_MANAGER and requested_price > 0:
        db.add(
            PriceChangeRequest(
                item_id=item.id,
                old_price=0,
                requested_price=requested_price,
                reason="Initial selling price",
                requested_by_id=actor.id,
            )
        )
    record_audit(
        db,
        actor=actor,
        action="create",
        category="inventory",
        entity_type="inventory_item",
        entity_id=item.id,
        summary=f"Created inventory item {item.name}",
        details={"sku": item.sku, "price_requires_approval": actor.role != UserRole.ROOT},
        ip_address=client_ip(request),
    )
    sync_auto_purchase_need(db, item=item, actor=actor)
    db.commit()
    return get_item_or_404(db, item.id)


@router.get("/items/{item_id}", response_model=InventoryItemRead)
def get_item(item_id: int, _: User = Depends(all_staff), db: Session = Depends(get_db)) -> InventoryItem:
    query = (
        select(InventoryItem)
        .options(selectinload(InventoryItem.category))
        .where(InventoryItem.id == item_id)
    )
    item = db.scalar(query)
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return item


@router.patch("/items/{item_id}", response_model=InventoryItemRead)
def update_item(
    item_id: int,
    payload: InventoryItemUpdate,
    request: Request,
    actor: User = Depends(inventory_roles),
    db: Session = Depends(get_db),
) -> InventoryItem:
    item = get_item_or_404(db, item_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if "sku" in changes:
        duplicate = db.scalar(
            select(InventoryItem.id).where(InventoryItem.sku == changes["sku"], InventoryItem.id != item_id)
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="SKU already exists")
    if "category_id" in changes and changes["category_id"] is not None:
        if db.get(Category, changes["category_id"]) is None:
            raise HTTPException(status_code=400, detail="Category does not exist")
    reorder_level = Decimal(changes.get("reorder_level", item.reorder_level))
    target_stock = Decimal(changes.get("target_stock_level", item.target_stock_level))
    auto_enabled = changes.get("auto_reorder_enabled", item.auto_reorder_enabled)
    if auto_enabled and target_stock <= reorder_level:
        raise HTTPException(
            status_code=422,
            detail="Target stock must be greater than the reorder level when automatic shopping is enabled",
        )
    for key, value in changes.items():
        setattr(item, key, value)
    record_audit(
        db,
        actor=actor,
        action="update",
        category="inventory",
        entity_type="inventory_item",
        entity_id=item.id,
        summary=f"Updated inventory item {item.name}",
        details={key: str(value) for key, value in changes.items()},
        ip_address=client_ip(request),
    )
    sync_auto_purchase_need(db, item=item, actor=actor)
    db.commit()
    return get_item(item.id, actor, db)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_item(
    item_id: int,
    request: Request,
    actor: User = Depends(inventory_roles),
    db: Session = Depends(get_db),
) -> None:
    item = get_item_or_404(db, item_id, lock=True)
    item.is_active = False
    sync_auto_purchase_need(db, item=item, actor=actor)
    record_audit(
        db,
        actor=actor,
        action="archive",
        category="inventory",
        entity_type="inventory_item",
        entity_id=item.id,
        summary=f"Archived inventory item {item.name}",
        ip_address=client_ip(request),
    )
    db.commit()


@router.post("/items/{item_id}/movements", response_model=MovementRead, status_code=201)
def create_movement(
    item_id: int,
    payload: MovementCreate,
    request: Request,
    actor: User = Depends(inventory_roles),
    db: Session = Depends(get_db),
) -> StockMovement:
    item = get_item_or_404(db, item_id, lock=True)
    before = Decimal(item.current_quantity)
    delta = payload.quantity
    if payload.movement_type == "waste":
        delta = -abs(delta)
    after = before + delta
    if after < 0:
        raise HTTPException(status_code=409, detail="Movement would make stock negative")
    if payload.movement_type == "receive" and payload.unit_cost is None:
        raise HTTPException(status_code=422, detail="Unit cost is required when receiving stock")

    movement_type = MovementType(payload.movement_type)
    movement = StockMovement(
        item_id=item.id,
        movement_type=movement_type,
        quantity=delta,
        unit_cost=payload.unit_cost,
        quantity_before=before,
        quantity_after=after,
        reason=payload.reason,
        created_by_id=actor.id,
    )
    if movement_type == MovementType.RECEIVE and payload.unit_cost is not None:
        received_value = delta * payload.unit_cost
        old_value = before * item.average_cost
        item.average_cost = (old_value + received_value) / after if after else payload.unit_cost
        item.last_purchase_price = payload.unit_cost
    item.current_quantity = after
    db.add(movement)
    db.flush()
    sync_auto_purchase_need(
        db,
        item=item,
        actor=actor,
        supply_received=movement_type == MovementType.RECEIVE,
    )
    record_audit(
        db,
        actor=actor,
        action=movement_type.value,
        category="inventory",
        entity_type="stock_movement",
        entity_id=movement.id,
        summary=f"{movement_type.value.title()} {abs(delta)} {item.unit} of {item.name}",
        details={"before": str(before), "after": str(after), "reason": payload.reason},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(movement)
    return movement


@router.get("/items/{item_id}/movements", response_model=list[MovementRead])
def list_movements(
    item_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(all_staff),
    db: Session = Depends(get_db),
) -> list[StockMovement]:
    get_item_or_404(db, item_id)
    return list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.item_id == item_id)
            .order_by(StockMovement.created_at.desc())
            .limit(limit)
        )
    )


@router.post("/items/{item_id}/price-requests", response_model=PriceRequestRead, status_code=201)
def request_price_change(
    item_id: int,
    payload: PriceRequestCreate,
    request: Request,
    actor: User = Depends(inventory_roles),
    db: Session = Depends(get_db),
) -> PriceChangeRequest:
    item = get_item_or_404(db, item_id, lock=True)
    if actor.role == UserRole.ROOT:
        old_price = item.selling_price
        item.selling_price = payload.requested_price
        price_request = PriceChangeRequest(
            item_id=item.id,
            old_price=old_price,
            requested_price=payload.requested_price,
            reason=payload.reason,
            status=ApprovalStatus.APPROVED,
            requested_by_id=actor.id,
            decided_by_id=actor.id,
            decision_note="Changed directly by root",
            decided_at=datetime.now(UTC).replace(tzinfo=None),
        )
    else:
        existing = db.scalar(
            select(PriceChangeRequest.id).where(
                PriceChangeRequest.item_id == item_id,
                PriceChangeRequest.status == ApprovalStatus.PENDING,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail="This item already has a pending price request")
        price_request = PriceChangeRequest(
            item_id=item.id,
            old_price=item.selling_price,
            requested_price=payload.requested_price,
            reason=payload.reason,
            requested_by_id=actor.id,
        )
    db.add(price_request)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="price_change_requested" if actor.role != UserRole.ROOT else "price_changed",
        category="approvals",
        entity_type="price_change_request",
        entity_id=price_request.id,
        summary=f"Requested {item.name} price change from {item.selling_price} to {payload.requested_price}",
        details={"reason": payload.reason},
        ip_address=client_ip(request),
    )
    db.commit()
    query = (
        select(PriceChangeRequest)
        .options(
            selectinload(PriceChangeRequest.item).selectinload(InventoryItem.category),
            selectinload(PriceChangeRequest.requested_by),
        )
        .where(PriceChangeRequest.id == price_request.id)
    )
    return db.scalar(query)


@router.get("/price-requests", response_model=list[PriceRequestRead])
def list_price_requests(
    approval_status: ApprovalStatus | None = Query(default=None, alias="status"),
    _: User = Depends(inventory_roles),
    db: Session = Depends(get_db),
) -> list[PriceChangeRequest]:
    query = select(PriceChangeRequest).options(
        selectinload(PriceChangeRequest.item).selectinload(InventoryItem.category),
        selectinload(PriceChangeRequest.requested_by),
    )
    if approval_status:
        query = query.where(PriceChangeRequest.status == approval_status)
    return list(db.scalars(query.order_by(PriceChangeRequest.created_at.desc()).limit(200)))


@router.post("/price-requests/{request_id}/decision", response_model=PriceRequestRead)
def decide_price_request(
    request_id: int,
    payload: ApprovalDecision,
    request: Request,
    actor: User = Depends(require_roles(UserRole.ROOT)),
    db: Session = Depends(get_db),
) -> PriceChangeRequest:
    price_request = db.scalar(
        select(PriceChangeRequest).where(PriceChangeRequest.id == request_id).with_for_update()
    )
    if price_request is None:
        raise HTTPException(status_code=404, detail="Price request not found")
    if price_request.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail="Price request has already been decided")
    item = get_item_or_404(db, price_request.item_id, lock=True)
    price_request.status = ApprovalStatus(payload.status)
    price_request.decided_by_id = actor.id
    price_request.decision_note = payload.note
    price_request.decided_at = datetime.now(UTC).replace(tzinfo=None)
    if price_request.status == ApprovalStatus.APPROVED:
        item.selling_price = price_request.requested_price
    record_audit(
        db,
        actor=actor,
        action=f"price_change_{payload.status}",
        category="approvals",
        entity_type="price_change_request",
        entity_id=price_request.id,
        summary=f"{payload.status.title()} price change for {item.name}",
        details={"old_price": str(price_request.old_price), "new_price": str(price_request.requested_price)},
        ip_address=client_ip(request),
    )
    db.commit()
    return db.scalar(
        select(PriceChangeRequest)
        .options(
            selectinload(PriceChangeRequest.item).selectinload(InventoryItem.category),
            selectinload(PriceChangeRequest.requested_by),
        )
        .where(PriceChangeRequest.id == request_id)
    )


@router.post("/items/{item_id}/image", response_model=InventoryItemRead)
async def upload_item_image(
    item_id: int,
    request: Request,
    image: UploadFile = File(...),
    actor: User = Depends(inventory_roles),
    db: Session = Depends(get_db),
) -> InventoryItem:
    item = get_item_or_404(db, item_id)
    extension = IMAGE_TYPES.get(image.content_type or "")
    if extension is None:
        raise HTTPException(status_code=415, detail="Use a JPG, PNG, or WebP image")
    contents = await image.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(contents) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Image must be under {settings.max_upload_mb} MB")
    target_dir = Path(settings.upload_dir) / "inventory"
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{item.id}-{uuid4().hex}{extension}"
    target = target_dir / filename
    target.write_bytes(contents)
    old_path = item.image_path
    item.image_path = f"/uploads/inventory/{filename}"
    record_audit(
        db,
        actor=actor,
        action="image_update",
        category="inventory",
        entity_type="inventory_item",
        entity_id=item.id,
        summary=f"Updated image for {item.name}",
        ip_address=client_ip(request),
    )
    db.commit()
    if old_path and old_path.startswith("/uploads/inventory/"):
        old_file = Path(settings.upload_dir) / "inventory" / Path(old_path).name
        old_file.unlink(missing_ok=True)
    return get_item(item.id, actor, db)


@router.get("/items/{item_id}/report")
def item_report(item_id: int, _: User = Depends(all_staff), db: Session = Depends(get_db)) -> dict:
    item = get_item_or_404(db, item_id)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=90)
    movements = list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.item_id == item_id, StockMovement.created_at >= since)
            .order_by(StockMovement.created_at)
        )
    )
    price_changes = list(
        db.scalars(
            select(PriceChangeRequest)
            .where(
                PriceChangeRequest.item_id == item_id,
                PriceChangeRequest.status == ApprovalStatus.APPROVED,
            )
            .order_by(PriceChangeRequest.created_at)
        )
    )
    daily: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"received": Decimal("0"), "used": Decimal("0"), "waste": Decimal("0")}
    )
    for movement in movements:
        key = movement.created_at.date().isoformat()
        if movement.movement_type == MovementType.RECEIVE:
            daily[key]["received"] += abs(movement.quantity)
        elif movement.movement_type == MovementType.WASTE:
            daily[key]["waste"] += abs(movement.quantity)
        elif movement.movement_type in {MovementType.SALE, MovementType.CONSUME}:
            daily[key]["used"] += abs(movement.quantity)
    total_used = sum((values["used"] for values in daily.values()), Decimal("0"))
    return {
        "item_id": item.id,
        "name": item.name,
        "stock_value": item.current_quantity * item.average_cost,
        "units_used_90d": total_used,
        "average_daily_use": total_used / Decimal("90"),
        "estimated_days_remaining": (
            item.current_quantity / (total_used / Decimal("90")) if total_used > 0 else None
        ),
        "daily_activity": [{"date": key, **values} for key, values in daily.items()],
        "price_history": [
            {
                "date": change.decided_at or change.created_at,
                "old_price": change.old_price,
                "new_price": change.requested_price,
            }
            for change in price_changes
        ],
    }
