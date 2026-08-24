from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit
from app.db import get_db
from app.deps import client_ip, require_roles
from app.models import (
    ApprovalStatus,
    DailyNeed,
    InventoryItem,
    MenuItem,
    Recipe,
    RecipeIngredient,
    User,
    UserRole,
)
from app.schemas import ApprovalDecision, DailyNeedCreate, DailyNeedRead, RecipeRead, RecipeUpsert

router = APIRouter(prefix="/kitchen", tags=["kitchen"])
kitchen_roles = require_roles(UserRole.ROOT, UserRole.KITCHEN_MANAGER)
needs_view_roles = require_roles(UserRole.ROOT, UserRole.KITCHEN_MANAGER, UserRole.STORAGE_MANAGER)
root_only = require_roles(UserRole.ROOT)


def recipe_query():
    return select(Recipe).options(
        selectinload(Recipe.menu_item),
        selectinload(Recipe.ingredients).selectinload(RecipeIngredient.inventory_item).selectinload(
            InventoryItem.category
        ),
    )


def serialize_recipe(recipe: Recipe) -> RecipeRead:
    cost = sum(
        (ingredient.quantity * ingredient.inventory_item.average_cost for ingredient in recipe.ingredients),
        Decimal("0"),
    ) / recipe.yield_quantity
    price = recipe.menu_item.selling_price
    percent = (cost / price * 100) if price > 0 else Decimal("0")
    result = RecipeRead.model_validate(recipe)
    result.calculated_cost = cost.quantize(Decimal("0.01"))
    result.food_cost_percent = percent.quantize(Decimal("0.01"))
    return result


def validate_ingredients(db: Session, payload: RecipeUpsert) -> None:
    ids = [line.inventory_item_id for line in payload.ingredients]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Each ingredient can appear only once")
    found = set(db.scalars(select(InventoryItem.id).where(InventoryItem.id.in_(ids))))
    if found != set(ids):
        raise HTTPException(status_code=422, detail="One or more inventory ingredients do not exist")


@router.get("/recipes", response_model=list[RecipeRead])
def list_recipes(_: User = Depends(kitchen_roles), db: Session = Depends(get_db)) -> list[RecipeRead]:
    recipes = list(db.scalars(recipe_query().order_by(Recipe.updated_at.desc())).unique())
    return [serialize_recipe(recipe) for recipe in recipes]


@router.post("/recipes", response_model=RecipeRead, status_code=status.HTTP_201_CREATED)
def create_recipe(
    payload: RecipeUpsert,
    request: Request,
    actor: User = Depends(kitchen_roles),
    db: Session = Depends(get_db),
) -> RecipeRead:
    menu_item = db.get(MenuItem, payload.menu_item_id)
    if menu_item is None:
        raise HTTPException(status_code=404, detail="Menu item not found")
    if db.scalar(select(Recipe.id).where(Recipe.menu_item_id == payload.menu_item_id)):
        raise HTTPException(status_code=409, detail="This menu item already has a recipe")
    validate_ingredients(db, payload)
    recipe = Recipe(
        menu_item_id=payload.menu_item_id,
        yield_quantity=payload.yield_quantity,
        preparation_minutes=payload.preparation_minutes,
        instructions=payload.instructions,
        notes=payload.notes,
        created_by_id=actor.id,
        ingredients=[
            RecipeIngredient(**ingredient.model_dump()) for ingredient in payload.ingredients
        ],
    )
    db.add(recipe)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="kitchen",
        entity_type="recipe",
        entity_id=recipe.id,
        summary=f"Created recipe for {menu_item.name}",
        details={"ingredients": len(payload.ingredients), "yield": str(payload.yield_quantity)},
        ip_address=client_ip(request),
    )
    db.commit()
    recipe = db.scalar(recipe_query().where(Recipe.id == recipe.id))
    return serialize_recipe(recipe)


@router.put("/recipes/{recipe_id}", response_model=RecipeRead)
def update_recipe(
    recipe_id: int,
    payload: RecipeUpsert,
    request: Request,
    actor: User = Depends(kitchen_roles),
    db: Session = Depends(get_db),
) -> RecipeRead:
    recipe = db.scalar(recipe_query().where(Recipe.id == recipe_id))
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if payload.menu_item_id != recipe.menu_item_id:
        duplicate = db.scalar(select(Recipe.id).where(Recipe.menu_item_id == payload.menu_item_id))
        if duplicate:
            raise HTTPException(status_code=409, detail="Selected menu item already has a recipe")
    menu_item = db.get(MenuItem, payload.menu_item_id)
    if menu_item is None:
        raise HTTPException(status_code=404, detail="Menu item not found")
    validate_ingredients(db, payload)
    recipe.menu_item_id = payload.menu_item_id
    recipe.yield_quantity = payload.yield_quantity
    recipe.preparation_minutes = payload.preparation_minutes
    recipe.instructions = payload.instructions
    recipe.notes = payload.notes
    recipe.ingredients.clear()
    recipe.ingredients.extend(
        RecipeIngredient(**ingredient.model_dump()) for ingredient in payload.ingredients
    )
    record_audit(
        db,
        actor=actor,
        action="update",
        category="kitchen",
        entity_type="recipe",
        entity_id=recipe.id,
        summary=f"Updated recipe for {menu_item.name}",
        details={"ingredients": len(payload.ingredients), "yield": str(payload.yield_quantity)},
        ip_address=client_ip(request),
    )
    db.commit()
    recipe = db.scalar(recipe_query().where(Recipe.id == recipe.id))
    return serialize_recipe(recipe)


@router.delete("/recipes/{recipe_id}", status_code=204)
def delete_recipe(
    recipe_id: int,
    request: Request,
    actor: User = Depends(kitchen_roles),
    db: Session = Depends(get_db),
) -> None:
    recipe = db.scalar(recipe_query().where(Recipe.id == recipe_id))
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    name = recipe.menu_item.name
    record_audit(
        db,
        actor=actor,
        action="delete",
        category="kitchen",
        entity_type="recipe",
        entity_id=recipe.id,
        summary=f"Deleted recipe for {name}",
        ip_address=client_ip(request),
    )
    db.delete(recipe)
    db.commit()


@router.get("/daily-needs", response_model=list[DailyNeedRead])
def list_daily_needs(
    required_date: date | None = None,
    approval_status: ApprovalStatus | None = Query(default=None, alias="status"),
    _: User = Depends(needs_view_roles),
    db: Session = Depends(get_db),
) -> list[DailyNeed]:
    query = select(DailyNeed).options(selectinload(DailyNeed.requested_by))
    if required_date:
        query = query.where(DailyNeed.required_date == required_date)
    else:
        query = query.where(DailyNeed.required_date >= date.today() - timedelta(days=7))
    if approval_status:
        query = query.where(DailyNeed.status == approval_status)
    return list(db.scalars(query.order_by(DailyNeed.required_date, DailyNeed.created_at.desc())))


@router.post("/daily-needs", response_model=DailyNeedRead, status_code=201)
def create_daily_need(
    payload: DailyNeedCreate,
    request: Request,
    actor: User = Depends(kitchen_roles),
    db: Session = Depends(get_db),
) -> DailyNeed:
    if payload.required_date < date.today():
        raise HTTPException(status_code=422, detail="Required date cannot be in the past")
    if payload.inventory_item_id is not None:
        inventory_item = db.get(InventoryItem, payload.inventory_item_id)
        if inventory_item is None:
            raise HTTPException(status_code=422, detail="Inventory item not found")
    need = DailyNeed(**payload.model_dump(), requested_by_id=actor.id)
    db.add(need)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="daily_needs",
        entity_type="daily_need",
        entity_id=need.id,
        summary=f"Requested {need.quantity} {need.unit} {need.item_name} for {need.required_date}",
        details={"priority": need.priority.value},
        ip_address=client_ip(request),
    )
    db.commit()
    return db.scalar(
        select(DailyNeed).options(selectinload(DailyNeed.requested_by)).where(DailyNeed.id == need.id)
    )


@router.post("/daily-needs/{need_id}/decision", response_model=DailyNeedRead)
def decide_daily_need(
    need_id: int,
    payload: ApprovalDecision,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> DailyNeed:
    need = db.scalar(select(DailyNeed).where(DailyNeed.id == need_id).with_for_update())
    if need is None:
        raise HTTPException(status_code=404, detail="Daily need not found")
    if need.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail="Request has already been decided")
    need.status = ApprovalStatus(payload.status)
    need.decided_by_id = actor.id
    need.decision_note = payload.note
    need.decided_at = datetime.now(UTC).replace(tzinfo=None)
    record_audit(
        db,
        actor=actor,
        action=f"daily_need_{payload.status}",
        category="approvals",
        entity_type="daily_need",
        entity_id=need.id,
        summary=f"{payload.status.title()} purchase need: {need.item_name}",
        details={"required_date": need.required_date.isoformat(), "quantity": str(need.quantity)},
        ip_address=client_ip(request),
    )
    db.commit()
    return db.scalar(
        select(DailyNeed).options(selectinload(DailyNeed.requested_by)).where(DailyNeed.id == need.id)
    )
