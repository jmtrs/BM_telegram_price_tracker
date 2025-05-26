# adapters/api/schemas.py
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class AlertCreateRequest(BaseModel):
    url: str = Field(..., description="The URL of the product to track.")
    target_price: float = Field(..., gt=0, description="The desired target price for the product.")


class ScrapedProductInfo(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    condition: Optional[str] = None
    image: Optional[HttpUrl] = None
    description: Optional[str] = None
    availability: Optional[str] = None
    color: Optional[str] = None
    storage: Optional[str] = None
    brand_name: Optional[str] = None
    clean_url: Optional[str] = None
    full_url: Optional[HttpUrl] = None
    status: str


class AlertResponse(BaseModel):
    id: UUID
    full_url: str
    clean_url: str
    target_price: float
    status_message: str
    scraped_product_info: ScrapedProductInfo
    inserted_at: datetime
    last_price: Optional[float] = None
    last_notified: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertDBRecord(BaseModel):
    """Represents the structure of an alert as fetched from the database."""
    id: UUID
    user_id: Optional[UUID] = None
    full_url: str
    clean_url: str
    target_price: float
    last_price: Optional[float] = None
    inserted_at: datetime
    last_notified: Optional[datetime] = None
    product_name: Optional[str] = None

    class Config:
        from_attributes = True


class UserAlertsResponse(BaseModel):
    alerts: List[AlertDBRecord]


class UserResponse(BaseModel):
    id: Optional[UUID] = None
    idp_user_id: str
    username: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True
