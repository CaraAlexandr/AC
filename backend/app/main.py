from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import Item


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Lab API", version="1.0.0", lifespan=lifespan)


class ItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    note: str = ""


class ItemOut(BaseModel):
    id: int
    title: str
    note: str

    model_config = {"from_attributes": True}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/items", response_model=list[ItemOut])
def list_items(db: Session = Depends(get_db)):
    rows = db.scalars(select(Item).order_by(Item.id)).all()
    return rows


@app.post("/api/items", response_model=ItemOut)
def create_item(body: ItemCreate, db: Session = Depends(get_db)):
    row = Item(title=body.title.strip(), note=body.note.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/api/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    row = db.get(Item, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row
