from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import (
    ApprovalStatus,
    DailyNeed,
    InventoryItem,
    MenuItem,
    NeedSource,
    Notification,
    Order,
    OrderStatus,
    PriceChangeRequest,
    PurchaseReceipt,
    PurchaseStatus,
    StockMovement,
    User,
    UserRole,
)
from app.schemas import DashboardSummary

router = APIRouter(tags=["reports"])
root_only = require_roles(UserRole.ROOT)


def day_bounds(value: date) -> tuple[datetime, datetime]:
    return datetime.combine(value, time.min), datetime.combine(value, time.max)


def successful_orders_query(start: datetime, end: datetime):
    return select(Order).where(
        Order.created_at.between(start, end),
        Order.status != OrderStatus.CANCELLED,
    )


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    actor: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> DashboardSummary:
    today_start, today_end = day_bounds(date.today())
    yesterday_start, yesterday_end = day_bounds(date.today() - timedelta(days=1))
    today_orders = list(db.scalars(successful_orders_query(today_start, today_end)))
    yesterday_orders = list(db.scalars(successful_orders_query(yesterday_start, yesterday_end)))
    sales_today = sum((order.total for order in today_orders), Decimal("0"))
    sales_yesterday = sum((order.total for order in yesterday_orders), Decimal("0"))
    sales_change = (
        ((sales_today - sales_yesterday) / sales_yesterday * 100)
        if sales_yesterday > 0
        else (Decimal("100") if sales_today > 0 else Decimal("0"))
    )
    recent = list(
        db.scalars(
            select(Order)
            .options(selectinload(Order.items))
            .order_by(Order.created_at.desc())
            .limit(6)
        ).unique()
    )
    low_stock = list(
        db.scalars(
            select(InventoryItem)
            .options(selectinload(InventoryItem.category))
            .where(
                InventoryItem.is_active.is_(True),
                InventoryItem.current_quantity <= InventoryItem.reorder_level,
            )
            .order_by((InventoryItem.current_quantity - InventoryItem.reorder_level))
            .limit(8)
        )
    )
    return DashboardSummary(
        sales_today=sales_today,
        orders_today=len(today_orders),
        average_order_value=sales_today / len(today_orders) if today_orders else 0,
        low_stock_count=db.scalar(
            select(func.count()).select_from(InventoryItem).where(
                InventoryItem.is_active.is_(True),
                InventoryItem.current_quantity <= InventoryItem.reorder_level,
            )
        )
        or 0,
        pending_price_approvals=db.scalar(
            select(func.count()).select_from(PriceChangeRequest).where(
                PriceChangeRequest.status == ApprovalStatus.PENDING
            )
        )
        or 0,
        pending_daily_needs=db.scalar(
            select(func.count()).select_from(DailyNeed).where(DailyNeed.status == ApprovalStatus.PENDING)
        )
        or 0,
        automatic_purchase_needs=db.scalar(
            select(func.count()).select_from(DailyNeed).where(
                DailyNeed.status == ApprovalStatus.PENDING,
                DailyNeed.source == NeedSource.AUTOMATIC,
            )
        )
        or 0,
        unread_notifications=db.scalar(
            select(func.count()).select_from(Notification).where(
                Notification.recipient_user_id == actor.id,
                Notification.is_read.is_(False),
            )
        )
        or 0,
        active_users=db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0,
        orders_in_kitchen=db.scalar(
            select(func.count()).select_from(Order).where(
                Order.status.in_([OrderStatus.CONFIRMED, OrderStatus.PREPARING])
            )
        )
        or 0,
        sales_change_percent=sales_change.quantize(Decimal("0.01")),
        recent_orders=recent,
        low_stock_items=low_stock,
    )


@router.get("/reports/overview")
def reports_overview(
    days: int = Query(default=30, ge=7, le=365),
    _: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> dict:
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    previous_start = start_date - timedelta(days=days)
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)
    previous_start_dt = datetime.combine(previous_start, time.min)
    previous_end_dt = start_dt - timedelta(microseconds=1)

    orders = list(
        db.scalars(
            successful_orders_query(start_dt, end_dt).options(selectinload(Order.items))
        ).unique()
    )
    previous_orders = list(db.scalars(successful_orders_query(previous_start_dt, previous_end_dt)))
    revenue = sum((order.total for order in orders), Decimal("0"))
    previous_revenue = sum((order.total for order in previous_orders), Decimal("0"))
    revenue_growth = (
        (revenue - previous_revenue) / previous_revenue * 100
        if previous_revenue > 0
        else (Decimal("100") if revenue > 0 else Decimal("0"))
    )

    menu_ids = {line.menu_item_id for order in orders for line in order.items}
    cogs = sum(
        (line.line_cost for order in orders for line in order.items),
        Decimal("0"),
    )
    purchase_spend = db.scalar(
        select(func.coalesce(func.sum(PurchaseReceipt.total_cost), 0)).where(
            PurchaseReceipt.purchased_at.between(start_dt, end_dt),
            PurchaseReceipt.status == PurchaseStatus.POSTED,
        )
    ) or Decimal("0")
    daily = {
        (start_date + timedelta(days=index)).isoformat(): {
            "date": (start_date + timedelta(days=index)).isoformat(),
            "revenue": Decimal("0"),
            "orders": 0,
        }
        for index in range(days)
    }
    product_stats: dict[int, dict] = {}
    hourly = {hour: {"hour": hour, "revenue": Decimal("0"), "orders": 0} for hour in range(24)}
    category_stats: dict[str, dict] = defaultdict(
        lambda: {"revenue": Decimal("0"), "quantity": 0}
    )
    customer_counts: Counter[int] = Counter()

    menu_lookup = {
        item.id: item
        for item in db.scalars(select(MenuItem).where(MenuItem.id.in_(menu_ids)))
    }
    for order in orders:
        key = order.created_at.date().isoformat()
        daily[key]["revenue"] += order.total
        daily[key]["orders"] += 1
        hourly[order.created_at.hour]["revenue"] += order.total
        hourly[order.created_at.hour]["orders"] += 1
        if order.customer_id:
            customer_counts[order.customer_id] += 1
        for line in order.items:
            allocated_revenue = (
                line.line_total * order.total / order.subtotal
                if order.subtotal > 0
                else Decimal("0")
            )
            stat = product_stats.setdefault(
                line.menu_item_id,
                {
                    "id": line.menu_item_id,
                    "name": line.name,
                    "quantity": 0,
                    "revenue": Decimal("0"),
                    "estimated_cost": Decimal("0"),
                },
            )
            stat["quantity"] += line.quantity
            stat["revenue"] += allocated_revenue
            stat["estimated_cost"] += line.line_cost
            menu = menu_lookup.get(line.menu_item_id)
            category = menu.category if menu else "Unknown"
            category_stats[category]["revenue"] += allocated_revenue
            category_stats[category]["quantity"] += line.quantity

    for stat in product_stats.values():
        stat["gross_profit"] = stat["revenue"] - stat["estimated_cost"]
        stat["margin_percent"] = (
            stat["gross_profit"] / stat["revenue"] * 100 if stat["revenue"] > 0 else Decimal("0")
        )

    inventory_items = list(db.scalars(select(InventoryItem).where(InventoryItem.is_active.is_(True))))
    inventory_value = sum(
        (item.current_quantity * item.average_cost for item in inventory_items), Decimal("0")
    )
    low_stock = [item for item in inventory_items if item.current_quantity <= item.reorder_level]
    since_30 = datetime.combine(end_date - timedelta(days=29), time.min)
    moving_ids = set(
        db.scalars(
            select(StockMovement.item_id).where(
                StockMovement.created_at >= since_30,
                StockMovement.quantity < 0,
            )
        )
    )
    slow_moving_value = sum(
        (item.current_quantity * item.average_cost for item in inventory_items if item.id not in moving_ids),
        Decimal("0"),
    )

    return {
        "period": {"days": days, "start": start_date, "end": end_date},
        "kpis": {
            "revenue": revenue,
            "revenue_growth_percent": revenue_growth.quantize(Decimal("0.01")),
            "orders": len(orders),
            "average_order_value": revenue / len(orders) if orders else Decimal("0"),
            "estimated_cogs": cogs.quantize(Decimal("0.01")),
            "purchase_spend": Decimal(purchase_spend).quantize(Decimal("0.01")),
            "gross_profit": (revenue - cogs).quantize(Decimal("0.01")),
            "gross_margin_percent": ((revenue - cogs) / revenue * 100).quantize(Decimal("0.01"))
            if revenue > 0
            else Decimal("0"),
            "known_customer_rate_percent": (
                Decimal(sum(1 for order in orders if order.customer_id)) / len(orders) * 100
            ).quantize(Decimal("0.01"))
            if orders
            else Decimal("0"),
            "repeat_customers": sum(1 for count in customer_counts.values() if count > 1),
        },
        "daily_sales": list(daily.values()),
        "hourly_demand": list(hourly.values()),
        "product_performance": sorted(
            product_stats.values(), key=lambda item: item["revenue"], reverse=True
        )[:20],
        "category_performance": [
            {"category": name, **values}
            for name, values in sorted(
                category_stats.items(), key=lambda item: item[1]["revenue"], reverse=True
            )
        ],
        "inventory_health": {
            "total_value": inventory_value.quantize(Decimal("0.01")),
            "active_items": len(inventory_items),
            "low_stock_items": len(low_stock),
            "automatic_purchase_needs": db.scalar(
                select(func.count()).select_from(DailyNeed).where(
                    DailyNeed.source == NeedSource.AUTOMATIC,
                    DailyNeed.status == ApprovalStatus.PENDING,
                )
            )
            or 0,
            "slow_moving_value": slow_moving_value.quantize(Decimal("0.01")),
            "slow_moving_percent": (slow_moving_value / inventory_value * 100).quantize(Decimal("0.01"))
            if inventory_value > 0
            else Decimal("0"),
        },
        "insights": build_insights(
            revenue=revenue,
            growth=revenue_growth,
            products=list(product_stats.values()),
            low_stock_count=len(low_stock),
            slow_moving_value=slow_moving_value,
            peak_hour=max(hourly.values(), key=lambda item: item["revenue"])["hour"] if orders else None,
        ),
    }


def build_insights(
    *,
    revenue: Decimal,
    growth: Decimal,
    products: list[dict],
    low_stock_count: int,
    slow_moving_value: Decimal,
    peak_hour: int | None,
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    if growth >= 10:
        insights.append({"tone": "positive", "title": "Revenue momentum", "message": f"Revenue grew {growth:.1f}% versus the previous period."})
    elif growth <= -10:
        insights.append({"tone": "warning", "title": "Revenue needs attention", "message": f"Revenue fell {abs(growth):.1f}% versus the previous period."})
    if products:
        best = max(products, key=lambda item: item["revenue"])
        insights.append({"tone": "info", "title": "Top revenue product", "message": f"{best['name']} generated the most revenue in this period."})
        low_margin = [item for item in products if item.get("margin_percent", 100) < 30]
        if low_margin:
            insights.append({"tone": "warning", "title": "Margin opportunity", "message": f"{len(low_margin)} product(s) have an estimated gross margin below 30%."})
    if peak_hour is not None:
        insights.append({"tone": "info", "title": "Peak sales hour", "message": f"Sales are strongest around {peak_hour:02d}:00; align staffing and preparation with this window."})
    if low_stock_count:
        insights.append({"tone": "critical", "title": "Stock risk", "message": f"{low_stock_count} inventory item(s) are at or below their reorder level."})
    if slow_moving_value > 0:
        insights.append({"tone": "neutral", "title": "Idle inventory", "message": "Some inventory value has had no consumption in the last 30 days; consider purchasing adjustments."})
    if revenue == 0:
        insights.append({"tone": "neutral", "title": "Start collecting signal", "message": "Record orders and recipe costs to unlock sales and margin recommendations."})
    return insights[:6]
