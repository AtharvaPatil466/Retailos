"""Store shelf map: freeform canvas sections with live inventory-linked products."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Product, ShelfSection, ShelfSectionProduct
from db.session import get_db

router = APIRouter(prefix="/shelf-map", tags=["shelf-map"])


class SectionUpdatePayload(BaseModel):
    name: str
    x: float
    y: float
    width: float
    height: float
    product_ids: list[str] = []


class SectionProductsPayload(BaseModel):
    product_ids: list[str] = []


async def _load_section(db: AsyncSession, section_id: int) -> ShelfSection | None:
    result = await db.execute(
        select(ShelfSection)
        .where(ShelfSection.id == section_id)
        .options(
            selectinload(ShelfSection.products).selectinload(ShelfSectionProduct.product)
        )
    )
    return result.scalar_one_or_none()


def _serialize_section(section: ShelfSection) -> dict:
    return {
        "id": section.id,
        "name": section.name,
        "x": section.x,
        "y": section.y,
        "width": section.width,
        "height": section.height,
        "store_id": section.store_id,
        "products": [
            {
                "product_id": link.product.id,
                "product_name": link.product.product_name,
                "current_stock": link.product.current_stock,
            }
            for link in section.products
            if link.product is not None
        ],
    }


async def _replace_section_products(db: AsyncSession, section_id: int, product_ids: list[str]) -> None:
    await db.execute(
        delete(ShelfSectionProduct).where(ShelfSectionProduct.section_id == section_id)
    )

    normalized_ids = []
    seen = set()
    for product_id in product_ids:
        if product_id in seen:
            continue
        normalized_ids.append(product_id)
        seen.add(product_id)

    if not normalized_ids:
        return

    products_result = await db.execute(
        select(Product.id).where(Product.id.in_(normalized_ids))
    )
    valid_ids = {row[0] for row in products_result.all()}

    for product_id in normalized_ids:
        if product_id in valid_ids:
            db.add(ShelfSectionProduct(section_id=section_id, product_id=product_id))

    await db.flush()


@router.get("")
async def get_shelf_map(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ShelfSection)
        .options(
            selectinload(ShelfSection.products).selectinload(ShelfSectionProduct.product)
        )
        .order_by(ShelfSection.id.asc())
    )
    sections = result.scalars().unique().all()
    return [_serialize_section(section) for section in sections]


@router.post("/section", status_code=status.HTTP_201_CREATED)
async def create_shelf_section(db: AsyncSession = Depends(get_db)):
    section = ShelfSection(
        name="New section",
        x=40,
        y=40,
        width=160,
        height=70,
    )
    db.add(section)
    await db.flush()
    await db.refresh(section)
    loaded = await _load_section(db, section.id)
    return _serialize_section(loaded or section)


@router.put("/section/{section_id}")
async def update_shelf_section(
    section_id: int,
    body: SectionUpdatePayload,
    db: AsyncSession = Depends(get_db),
):
    section = await _load_section(db, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Shelf section not found")

    section.name = body.name
    section.x = body.x
    section.y = body.y
    section.width = body.width
    section.height = body.height

    await db.flush()
    await _replace_section_products(db, section_id, body.product_ids)

    updated = await _load_section(db, section_id)
    return _serialize_section(updated or section)


@router.delete("/section/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shelf_section(section_id: int, db: AsyncSession = Depends(get_db)):
    section = await db.get(ShelfSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Shelf section not found")

    await db.delete(section)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/section/{section_id}/products")
async def replace_shelf_section_products(
    section_id: int,
    body: SectionProductsPayload,
    db: AsyncSession = Depends(get_db),
):
    section = await _load_section(db, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Shelf section not found")

    await _replace_section_products(db, section_id, body.product_ids)
    updated = await _load_section(db, section_id)
    return {
        "section_id": section_id,
        "products": _serialize_section(updated or section)["products"],
    }
