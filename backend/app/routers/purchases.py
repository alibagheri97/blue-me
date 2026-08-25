from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit
from app.db import get_db
from app.deps import client_ip, require_roles
from app.models import (
    InventoryItem,
    MovementType,
    PurchaseLine,
    PurchaseReceipt,
    PurchaseStatus,
    StockMovement,
    User,
    UserRole,
)
from app.schemas import (
    PaginatedPurchases,
    PurchaseReceiptCreate,
    PurchaseReceiptRead,
    PurchaseVoid,
)
from app.services.inventory_alerts import sync_auto_purchase_need

router = APIRouter(prefix="/purchases", tags=["purchases"])
purchase_roles = require_roles(UserRole.ROOT, UserRole.STORAGE_MANAGER)
root_only = require_roles(UserRole.ROOT)
CENT = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


def receipt_query():
    return select(PurchaseReceipt).options(
        selectinload(PurchaseReceipt.created_by),
        selectinload(PurchaseReceipt.lines),
    )


def get_receipt_or_404(db: Session, receipt_id: int, *, lock: bool = False) -> PurchaseReceipt:
    query = receipt_query().where(PurchaseReceipt.id == receipt_id)
    if lock:
        query = query.with_for_update()
    receipt = db.scalar(query)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Purchase receipt not found")
    return receipt


@router.get("", response_model=PaginatedPurchases)
def list_purchases(
    search: str | None = Query(default=None, max_length=160),
    purchased_from: date | None = None,
    purchased_to: date | None = None,
    receipt_status: PurchaseStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(purchase_roles),
    db: Session = Depends(get_db),
) -> PaginatedPurchases:
    filters = []
    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                PurchaseReceipt.receipt_number.ilike(term),
                PurchaseReceipt.supplier_name.ilike(term),
                PurchaseReceipt.invoice_number.ilike(term),
            )
        )
    if purchased_from:
        filters.append(PurchaseReceipt.purchased_at >= datetime.combine(purchased_from, time.min))
    if purchased_to:
        filters.append(PurchaseReceipt.purchased_at <= datetime.combine(purchased_to, time.max))
    if receipt_status:
        filters.append(PurchaseReceipt.status == receipt_status)
    total = db.scalar(select(func.count()).select_from(PurchaseReceipt).where(*filters)) or 0
    items = list(
        db.scalars(
            receipt_query()
            .where(*filters)
            .order_by(PurchaseReceipt.purchased_at.desc(), PurchaseReceipt.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).unique()
    )
    return PaginatedPurchases(items=items, total=total, page=page, page_size=page_size)


@router.get("/{receipt_id}", response_model=PurchaseReceiptRead)
def get_purchase(
    receipt_id: int,
    _: User = Depends(purchase_roles),
    db: Session = Depends(get_db),
) -> PurchaseReceipt:
    return get_receipt_or_404(db, receipt_id)


@router.post("", response_model=PurchaseReceiptRead, status_code=status.HTTP_201_CREATED)
def create_purchase(
    payload: PurchaseReceiptCreate,
    request: Request,
    actor: User = Depends(purchase_roles),
    db: Session = Depends(get_db),
) -> PurchaseReceipt:
    item_ids = sorted(line.inventory_item_id for line in payload.lines)
    items = {
        item.id: item
        for item in db.scalars(
            select(InventoryItem)
            .where(InventoryItem.id.in_(item_ids), InventoryItem.is_active.is_(True))
            .order_by(InventoryItem.id)
            .with_for_update()
        )
    }
    if len(items) != len(item_ids):
        raise HTTPException(status_code=422, detail="One or more inventory items are unavailable")

    subtotal = sum((line.line_total for line in payload.lines), Decimal("0")).quantize(CENT)
    total_cost = (subtotal + payload.extra_cost - payload.discount).quantize(CENT)
    net_adjustment = payload.extra_cost - payload.discount
    receipt = PurchaseReceipt(
        receipt_number=f"PUR-{payload.purchased_at:%y%m%d}-{uuid4().hex[:6].upper()}",
        supplier_name=payload.supplier_name,
        invoice_number=payload.invoice_number,
        purchased_at=payload.purchased_at.replace(tzinfo=None),
        subtotal=subtotal,
        discount=payload.discount,
        extra_cost=payload.extra_cost,
        total_cost=total_cost,
        notes=payload.notes,
        created_by_id=actor.id,
    )
    db.add(receipt)
    db.flush()

    allocated_so_far = Decimal("0")
    audit_lines: list[dict[str, str]] = []
    for index, line_payload in enumerate(payload.lines):
        item = items[line_payload.inventory_item_id]
        stock_quantity = line_payload.quantity * line_payload.conversion_factor
        if index == len(payload.lines) - 1:
            allocated = (net_adjustment - allocated_so_far).quantize(CENT)
        elif subtotal > 0:
            allocated = (net_adjustment * line_payload.line_total / subtotal).quantize(
                CENT
            )
        else:
            allocated = (net_adjustment / len(payload.lines)).quantize(CENT)
        allocated_so_far += allocated
        landed_total = (line_payload.line_total + allocated).quantize(CENT)
        if landed_total < 0:
            raise HTTPException(status_code=422, detail="Allocated line cost cannot be negative")
        unit_cost = (landed_total / stock_quantity).quantize(FOUR_PLACES)
        before = Decimal(item.current_quantity)
        after = before + stock_quantity
        old_value = before * Decimal(item.average_cost)
        item.current_quantity = after
        item.average_cost = (old_value + landed_total) / after
        item.last_purchase_price = unit_cost

        line = PurchaseLine(
            receipt_id=receipt.id,
            inventory_item_id=item.id,
            item_name=item.name,
            quantity=line_payload.quantity,
            purchase_unit=line_payload.purchase_unit,
            conversion_factor=line_payload.conversion_factor,
            stock_quantity=stock_quantity,
            stock_unit=item.unit,
            line_total=line_payload.line_total,
            allocated_cost=allocated,
            landed_total=landed_total,
            unit_cost=unit_cost,
        )
        db.add(line)
        db.add(
            StockMovement(
                item_id=item.id,
                movement_type=MovementType.RECEIVE,
                quantity=stock_quantity,
                unit_cost=unit_cost,
                quantity_before=before,
                quantity_after=after,
                reason=f"ورود از فاکتور {receipt.receipt_number}",
                reference_type="purchase_receipt",
                reference_id=receipt.id,
                created_by_id=actor.id,
            )
        )
        sync_auto_purchase_need(db, item=item, actor=actor, supply_received=True)
        audit_lines.append(
            {
                "item": item.name,
                "purchased": f"{line_payload.quantity} {line_payload.purchase_unit}",
                "stock_added": f"{stock_quantity} {item.unit}",
                "landed_total": str(landed_total),
            }
        )

    record_audit(
        db,
        actor=actor,
        action="create",
        category="purchases",
        entity_type="purchase_receipt",
        entity_id=receipt.id,
        summary=f"Posted purchase receipt {receipt.receipt_number} with {len(payload.lines)} items",
        details={
            "supplier": payload.supplier_name,
            "invoice_number": payload.invoice_number,
            "subtotal": str(subtotal),
            "discount": str(payload.discount),
            "extra_cost": str(payload.extra_cost),
            "total_cost": str(total_cost),
            "lines": audit_lines,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    db.expire_all()
    return get_receipt_or_404(db, receipt.id)


@router.post("/{receipt_id}/void", response_model=PurchaseReceiptRead)
def void_purchase(
    receipt_id: int,
    payload: PurchaseVoid,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> PurchaseReceipt:
    receipt = get_receipt_or_404(db, receipt_id, lock=True)
    if receipt.status == PurchaseStatus.VOIDED:
        raise HTTPException(status_code=409, detail="Purchase receipt is already voided")
    item_ids = sorted(line.inventory_item_id for line in receipt.lines)
    items = {
        item.id: item
        for item in db.scalars(
            select(InventoryItem)
            .where(InventoryItem.id.in_(item_ids))
            .order_by(InventoryItem.id)
            .with_for_update()
        )
    }
    shortages = []
    for line in receipt.lines:
        item = items.get(line.inventory_item_id)
        if item is None:
            shortages.append(f"{line.item_name}: کالای انبار در دسترس نیست")
        elif Decimal(item.current_quantity) < Decimal(line.stock_quantity):
            shortages.append(
                f"{line.item_name}: نیاز به {line.stock_quantity}، موجودی {item.current_quantity}"
            )
    if shortages:
        raise HTTPException(
            status_code=409,
            detail={"message": "موجودی برای ابطال فاکتور کافی نیست", "items": shortages},
        )

    for line in receipt.lines:
        item = items[line.inventory_item_id]
        before = Decimal(item.current_quantity)
        after = before - Decimal(line.stock_quantity)
        remaining_value = before * Decimal(item.average_cost) - Decimal(line.landed_total)
        item.current_quantity = after
        item.average_cost = max(remaining_value, Decimal("0")) / after if after else Decimal("0")
        db.add(
            StockMovement(
                item_id=item.id,
                movement_type=MovementType.ADJUST,
                quantity=-Decimal(line.stock_quantity),
                unit_cost=line.unit_cost,
                quantity_before=before,
                quantity_after=after,
                reason=f"ابطال فاکتور {receipt.receipt_number}: {payload.reason}",
                reference_type="purchase_void",
                reference_id=receipt.id,
                created_by_id=actor.id,
            )
        )
        sync_auto_purchase_need(db, item=item, actor=actor)

    receipt.status = PurchaseStatus.VOIDED
    receipt.voided_by_id = actor.id
    receipt.voided_at = datetime.now(UTC).replace(tzinfo=None)
    receipt.void_reason = payload.reason
    record_audit(
        db,
        actor=actor,
        action="void",
        category="purchases",
        entity_type="purchase_receipt",
        entity_id=receipt.id,
        summary=f"Voided purchase receipt {receipt.receipt_number}",
        details={"reason": payload.reason, "total_cost": str(receipt.total_cost)},
        ip_address=client_ip(request),
    )
    db.commit()
    db.expire_all()
    return get_receipt_or_404(db, receipt.id)
