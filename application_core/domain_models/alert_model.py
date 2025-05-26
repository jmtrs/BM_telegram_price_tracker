# application_core/domain_models/alert_model.py
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, validator


class Alert(BaseModel):
    id: UUID
    user_id: UUID
    full_url: HttpUrl
    clean_url: HttpUrl
    target_price: float = Field(..., gt=0)
    last_price: Optional[float] = None
    last_notified: Optional[datetime] = None
    inserted_at: datetime = Field(default_factory=datetime.utcnow)
    product_name: Optional[str] = None
    @validator('clean_url')
    def clean_url_must_be_clean(cls, v: HttpUrl) -> HttpUrl:
        # Additional normalization/validation if needed
        return v

    @validator('last_price')
    def last_price_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError('last_price must be non-negative')
        return v

    class Config:
        orm_mode = True
