"""Read-only purchasing ledger. Inventory acquisitions are not charged to profit twice."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.deps import require_sections
from app.models import (
    Category,
    InventoryItem,
    MovementType,
    PurchaseLine,
    PurchaseReceipt,
    SectionKey,
    StockMovement,
    User,
)
from app.routers.purchases import get_receipt_or_404
from app.schemas import PurchaseReceiptRead
from app.services.business_time import (
    business_datetime,
    business_today,
    day_bounds,
    local_day_bounds,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])
expense_access = require_sections(SectionKey.EXPENSES)
ZERO = Decimal("0")
CENT = Decimal("0.01")


def operational_purchase_filter():
    """Legacy opening balances are stock valuations, not purchasing expenses.

    The bootstrap receipts use the explicit temporary-opening supplier label and
    reserved OPENING- invoice references (including supplementary receipts).
    Keep the records and their stock movements intact; exclude only this ledger.
    COALESCE is essential: genuine purchases may have no supplier or invoice.
    """
    return ~or_(
        func.trim(func.coalesce(PurchaseReceipt.supplier_name, ""))
        == "موجودی اولیه موقت",
        func.upper(func.trim(func.coalesce(PurchaseReceipt.invoice_number, ""))).like(
            "OPENING-%"
        ),
    )


def expense_filters(
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = None,
    end_date: date | None = None,
    search: str = Query(default="", max_length=160),
    category_id: int | None = Query(default=None, ge=0),
    item_id: int | None = Query(default=None, ge=1),
    supplier: str | None = Query(default=None, max_length=160),
    source: Literal["all", "purchase", "manual"] = "all",
) -> dict:
    if bool(start_date) != bool(end_date):
        raise HTTPException(422, "Select both start and end dates")
    end_date = end_date or business_today()
    start_date = start_date or end_date - timedelta(days=days - 1)
    if not 1 <= (end_date - start_date).days + 1 <= 365:
        raise HTTPException(422, "Report range must be between 1 and 365 days")
    return dict(
        start=start_date,
        end=end_date,
        search=search.strip(),
        category_id=category_id,
        item_id=item_id,
        supplier=supplier,
        source=source,
    )


def ledger_rows(db: Session, filters: dict) -> list[dict]:
    """Two projected queries, no lazy-loaded relationships or duplicate receipt movements.

    Receipt dates are business-local; direct movements have UTC timestamps. Prices
    and units come from receipt snapshots, never today's inventory prices.
    """
    common = []
    if filters["category_id"] is not None:
        common.append(
            InventoryItem.category_id == filters["category_id"]
            if filters["category_id"]
            else InventoryItem.category_id.is_(None)
        )
    if filters["item_id"]:
        common.append(InventoryItem.id == filters["item_id"])
    rows = []
    if filters["source"] != "manual":
        start, _ = local_day_bounds(filters["start"])
        _, end = local_day_bounds(filters["end"])
        query = (
            select(
                PurchaseLine.id.label("line_id"),
                PurchaseLine.inventory_item_id.label("item_id"),
                PurchaseLine.item_name,
                PurchaseLine.quantity,
                PurchaseLine.purchase_unit,
                PurchaseLine.stock_quantity,
                PurchaseLine.stock_unit,
                PurchaseLine.line_total,
                PurchaseLine.allocated_cost,
                PurchaseLine.landed_total,
                PurchaseLine.unit_cost,
                PurchaseReceipt.id.label("source_id"),
                PurchaseReceipt.receipt_number,
                PurchaseReceipt.supplier_name,
                PurchaseReceipt.invoice_number,
                PurchaseReceipt.purchased_at,
                PurchaseReceipt.status,
                PurchaseReceipt.total_cost.label("receipt_total"),
                PurchaseReceipt.notes,
                User.full_name.label("created_by"),
                Category.name.label("category"),
                InventoryItem.is_active,
            )
            .join(PurchaseReceipt, PurchaseReceipt.id == PurchaseLine.receipt_id)
            .join(
                InventoryItem,
                InventoryItem.id == PurchaseLine.inventory_item_id,
            )
            .outerjoin(Category, Category.id == InventoryItem.category_id)
            .join(
                User,
                User.id == PurchaseReceipt.created_by_id,
            )
            .where(
                PurchaseReceipt.purchased_at.between(start, end),
                operational_purchase_filter(),
                *common,
            )
        )
        if filters["supplier"] is not None:
            query = query.where(
                or_(
                    PurchaseReceipt.supplier_name.is_(None),
                    PurchaseReceipt.supplier_name == "",
                )
                if filters["supplier"] == ""
                else PurchaseReceipt.supplier_name == filters["supplier"]
            )
        if filters["search"]:
            term = f"%{filters['search']}%"
            query = query.where(
                or_(
                    PurchaseReceipt.receipt_number.ilike(term),
                    PurchaseReceipt.invoice_number.ilike(term),
                    PurchaseReceipt.supplier_name.ilike(term),
                    PurchaseLine.item_name.ilike(term),
                    InventoryItem.sku.ilike(term),
                )
            )
        for row in db.execute(query).mappings():
            rows.append({**row, "source": "purchase", "status": row["status"].value})
    if filters["source"] != "purchase" and filters["supplier"] in (None, ""):
        start, _ = day_bounds(filters["start"])
        _, end = day_bounds(filters["end"])
        query = (
            select(
                StockMovement.id,
                StockMovement.item_id,
                StockMovement.quantity,
                StockMovement.unit_cost,
                StockMovement.created_at,
                StockMovement.reason,
                InventoryItem.name.label("item_name"),
                InventoryItem.unit,
                InventoryItem.is_active,
                User.full_name.label("created_by"),
                Category.name.label("category"),
            )
            .join(InventoryItem, InventoryItem.id == StockMovement.item_id)
            .join(
                User,
                User.id == StockMovement.created_by_id,
            )
            .outerjoin(Category, Category.id == InventoryItem.category_id)
            .where(
                StockMovement.movement_type == MovementType.RECEIVE,
                StockMovement.quantity > 0,
                or_(
                    StockMovement.reference_type.is_(None),
                    StockMovement.reference_type != "purchase_receipt",
                ),
                StockMovement.created_at.between(start, end),
                *common,
            )
        )
        if filters["search"]:
            term = f"%{filters['search']}%"
            query = query.where(
                or_(
                    InventoryItem.name.ilike(term),
                    InventoryItem.sku.ilike(term),
                    StockMovement.reason.ilike(term),
                )
            )
        for row in db.execute(query).mappings():
            amount = (row["quantity"] * (row["unit_cost"] or ZERO)).quantize(CENT)
            rows.append(
                dict(
                    source="manual",
                    source_id=row["id"],
                    line_id=row["id"],
                    item_id=row["item_id"],
                    item_name=row["item_name"],
                    quantity=row["quantity"],
                    purchase_unit=row["unit"],
                    stock_quantity=row["quantity"],
                    stock_unit=row["unit"],
                    line_total=amount,
                    allocated_cost=ZERO,
                    landed_total=amount,
                    unit_cost=row["unit_cost"] or ZERO,
                    receipt_number=f"MOV-{row['id']}",
                    supplier_name=None,
                    invoice_number=None,
                    purchased_at=business_datetime(row["created_at"]).replace(
                        tzinfo=None
                    ),
                    status="posted",
                    receipt_total=amount,
                    notes=row["reason"],
                    created_by=row["created_by"],
                    category=row["category"],
                    is_active=row["is_active"],
                )
            )
    for row in rows:
        row["business_day"] = (
            (row["purchased_at"] - timedelta(hours=settings.business_day_start_hour))
            .date()
            .isoformat()
        )
        row["category"] = row["category"] or "بدون دسته‌بندی"
    return sorted(
        rows,
        key=lambda r: (r["purchased_at"], r["source"], r["source_id"], r["line_id"]),
    )


def decimal_strings(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: decimal_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decimal_strings(item) for item in value]
    return value


def price_summary(rows: list[dict]) -> dict:
    first, last = rows[0], rows[-1]
    amount = sum((r["landed_total"] for r in rows), ZERO)
    stock = sum((r["stock_quantity"] for r in rows), ZERO)
    difference = last["unit_cost"] - first["unit_cost"]
    return dict(
        item_id=last["item_id"],
        name=last["item_name"],
        unit=last["stock_unit"],
        category=last["category"],
        is_active=last["is_active"],
        total_cost=amount,
        quantity=stock,
        purchases=len(rows),
        first_price=first["unit_cost"],
        last_price=last["unit_cost"],
        min_price=min(r["unit_cost"] for r in rows),
        max_price=max(r["unit_cost"] for r in rows),
        average_price=(amount / stock).quantize(Decimal("0.0001")) if stock else ZERO,
        change=difference,
        change_percent=(difference / first["unit_cost"] * 100).quantize(CENT)
        if first["unit_cost"]
        else None,
        last_date=last["business_day"],
    )


@router.get("/options")
def expense_options(
    _: User = Depends(expense_access), db: Session = Depends(get_db)
) -> dict:
    return {
        "items": [
            dict(r)
            for r in db.execute(
                select(
                    InventoryItem.id,
                    InventoryItem.name,
                    InventoryItem.category_id,
                    InventoryItem.is_active,
                ).order_by(InventoryItem.name)
            ).mappings()
        ],
        "categories": [
            dict(r)
            for r in db.execute(
                select(Category.id, Category.name).order_by(Category.name)
            ).mappings()
        ],
        "suppliers": list(
            db.scalars(
                select(PurchaseReceipt.supplier_name)
                .where(
                    PurchaseReceipt.supplier_name.is_not(None),
                    PurchaseReceipt.supplier_name != "",
                    operational_purchase_filter(),
                )
                .distinct()
                .order_by(PurchaseReceipt.supplier_name)
            )
        ),
    }


@router.get("")
def expense_overview(
    filters: dict = Depends(expense_filters),
    receipt_status: Literal["all", "posted", "voided"] = "all",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=15, ge=1, le=100),
    _: User = Depends(expense_access),
    db: Session = Depends(get_db),
) -> dict:
    rows = ledger_rows(db, filters)
    receipts, products = {}, defaultdict(list)
    categories, suppliers = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    daily = {
        (filters["start"] + timedelta(days=i)).isoformat(): dict(
            cost=ZERO, purchase=ZERO, manual=ZERO
        )
        for i in range((filters["end"] - filters["start"]).days + 1)
    }
    goods, adjustment, manual, purchases = ZERO, ZERO, ZERO, ZERO
    for row in rows:
        key = f"{row['source']}:{row['source_id']}"
        receipt = receipts.setdefault(
            key,
            dict(
                key=key,
                source=row["source"],
                id=row["source_id"],
                receipt_number=row["receipt_number"],
                supplier_name=row["supplier_name"],
                invoice_number=row["invoice_number"],
                purchased_at=row["purchased_at"],
                business_day=row["business_day"],
                status=row["status"],
                total_cost=row["receipt_total"],
                matched_cost=ZERO,
                line_count=0,
                item_names=[],
                created_by=row["created_by"],
                notes=row["notes"],
                manual_line={
                    "quantity": row["quantity"],
                    "unit": row["stock_unit"],
                    "unit_cost": row["unit_cost"],
                }
                if row["source"] == "manual"
                else None,
            ),
        )
        receipt["matched_cost"] += row["landed_total"]
        receipt["line_count"] += 1
        if len(receipt["item_names"]) < 3:
            receipt["item_names"].append(row["item_name"])
        if row["status"] != "posted":
            continue
        amount = row["landed_total"]
        goods += row["line_total"]
        adjustment += row["allocated_cost"]
        if row["source"] == "manual":
            manual += amount
        else:
            purchases += amount
        daily[row["business_day"]]["cost"] += amount
        daily[row["business_day"]][row["source"]] += amount
        categories[row["category"]] += amount
        suppliers[row["supplier_name"] or "بدون فروشنده / ورود مستقیم"] += amount
        # Historic units can differ after inventory edits; never compare unlike units.
        products[(row["item_id"], row["stock_unit"])].append(row)
    receipt_list = sorted(
        receipts.values(), key=lambda r: (r["purchased_at"], r["key"]), reverse=True
    )
    posted = [r for r in receipt_list if r["status"] == "posted"]
    filtered = [
        r
        for r in receipt_list
        if receipt_status == "all" or r["status"] == receipt_status
    ]
    items = sorted(
        (price_summary(group) for group in products.values()),
        key=lambda p: p["total_cost"],
        reverse=True,
    )
    return decimal_strings(
        dict(
            period={
                "start": filters["start"],
                "end": filters["end"],
                "days": len(daily),
            },
            kpis=dict(
                total_cost=purchases + manual,
                purchase_cost=purchases,
                manual_cost=manual,
                goods_cost=goods,
                net_adjustment=adjustment,
                posted_count=len(posted),
                purchase_count=sum(r["source"] == "purchase" for r in posted),
                manual_count=sum(r["source"] == "manual" for r in posted),
                voided_count=sum(r["status"] == "voided" for r in receipt_list),
                item_count=len(products),
                price_increases=sum(
                    p["purchases"] > 1 and p["change"] > 0 for p in items
                ),
            ),
            daily=[{"date": day, **amounts} for day, amounts in daily.items()],
            categories=[
                {"name": name, "cost": cost}
                for name, cost in sorted(
                    categories.items(), key=lambda r: r[1], reverse=True
                )
            ],
            suppliers=[
                {"name": name, "cost": cost}
                for name, cost in sorted(
                    suppliers.items(), key=lambda r: r[1], reverse=True
                )
            ],
            items=items,
            receipts={
                "items": filtered[(page - 1) * page_size : page * page_size],
                "total": len(filtered),
                "page": page,
                "page_size": page_size,
            },
        )
    )


@router.get("/items/{inventory_item_id}/prices")
def item_prices(
    inventory_item_id: int,
    stock_unit: str = Query(min_length=1, max_length=32),
    filters: dict = Depends(expense_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(expense_access),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(InventoryItem, inventory_item_id) is None:
        raise HTTPException(404, "Inventory item not found")
    rows = [
        r
        for r in ledger_rows(db, {**filters, "item_id": inventory_item_id})
        if r["status"] == "posted" and r["stock_unit"] == stock_unit
    ]
    # Keep every purchase in the paginated ledger; daily chart contains at most 365 points.
    daily = {}
    previous = None
    for row in rows:
        row["change"] = row["unit_cost"] - previous if previous is not None else None
        row["change_percent"] = (
            ((row["unit_cost"] - previous) / previous * 100).quantize(CENT)
            if previous
            else None
        )
        previous = row["unit_cost"]
        daily[row["business_day"]] = {
            "date": row["business_day"],
            "price": row["unit_cost"],
        }
    newest = list(reversed(rows))
    return decimal_strings(
        {
            "summary": price_summary(rows) if rows else None,
            "daily": list(daily.values()),
            "items": newest[(page - 1) * page_size : page * page_size],
            "total": len(rows),
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/receipts/{receipt_id}", response_model=PurchaseReceiptRead)
def expense_receipt(
    receipt_id: int, _: User = Depends(expense_access), db: Session = Depends(get_db)
):
    # Expenses permission grants read-only details, not permission to post/void stock.
    if (
        db.scalar(
            select(PurchaseReceipt.id).where(
                PurchaseReceipt.id == receipt_id, operational_purchase_filter()
            )
        )
        is None
    ):
        raise HTTPException(404, "Purchase receipt not found")
    return get_receipt_or_404(db, receipt_id)


@router.get("/export")
def export_expenses(
    filters: dict = Depends(expense_filters),
    _: User = Depends(expense_access),
    db: Session = Depends(get_db),
):
    return decimal_strings({"items": ledger_rows(db, filters)})
