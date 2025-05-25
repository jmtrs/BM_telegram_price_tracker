# adapters/api/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class AlertCreateRequest(BaseModel):
    url: str = Field(..., description="The URL of the product to track.")
    target_price: float = Field(..., gt=0, description="The desired target price for the product.")
    # This will eventually come from the Logto token, not the request body directly.
    # For now, the client will need to provide it.
    idp_user_id: str = Field(..., description="The identity provider user ID.")

class ScrapedProductInfo(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    condition: Optional[str] = None
    image: Optional[str] = None
    description: Optional[str] = None
    availability: Optional[str] = None
    color: Optional[str] = None
    storage: Optional[str] = None
    brand_name: Optional[str] = None
    clean_url: Optional[str] = None # clean_url might not always be part of raw scrape dict
    full_url: Optional[str] = None  # full_url might not always be part of raw scrape dict
    status: str # Status of the scraping attempt (e.g., CACHE_HIT, SCRAPED_SUCCESS, SCRAPE_FAILED_TIMEOUT)

class AlertResponse(BaseModel):
    id: UUID
    chat_id: Optional[int] = None # Made chat_id optional
    full_url: str
    clean_url: str
    target_price: float
    status_message: str
    scraped_product_info: ScrapedProductInfo
    inserted_at: datetime # From the alerts table
    last_price: Optional[float] = None # From the alerts table
    last_notified: Optional[datetime] = None # From the alerts table

    class Config:
        orm_mode = True # For compatibility if returning ORM objects directly, though we build manually here

class AlertDBRecord(BaseModel):
    """Represents the structure of an alert as fetched from the database."""
    id: UUID
    chat_id: int
    user_id: Optional[UUID] = None # If you add user_id UUID to alerts table
    full_url: str
    clean_url: str
    target_price: float
    last_price: Optional[float] = None
    inserted_at: datetime
    last_notified: Optional[datetime] = None
    product_name: Optional[str] = None # This might be from a join or not directly on alert

    class Config:
        orm_mode = True

class UserAlertsResponse(BaseModel):
    alerts: List[AlertDBRecord]
