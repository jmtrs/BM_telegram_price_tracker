# application_core/domain_models/product_info_model.py
from typing import Optional
from pydantic import BaseModel, HttpUrl, validator


class ProductInfo(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    product_condition: Optional[str] = None  # e.g., "New", "Used"
    image_url: Optional[HttpUrl] = None
    description: Optional[str] = None
    availability: Optional[str] = None  # e.g., "InStock", "OutOfStock"
    color: Optional[str] = None
    storage: Optional[str] = None  # For products like phones
    brand_name: Optional[str] = None
    clean_url: str  # Normalized URL
    full_url: HttpUrl  # Original URL provided
    status: str  # e.g., "CACHE_HIT", "SCRAPED_SUCCESS", "SCRAPE_FAILED"

    @validator('price')
    def price_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError('price must be non-negative')
        return v

    @validator('status')
    def valid_status(cls, v: str) -> str:
        allowed_prefix = 'SCRAPE_FAILED'
        allowed = {'CACHE_HIT', 'SCRAPED_SUCCESS'}
        if v in allowed or v.startswith(allowed_prefix):
            return v
        raise ValueError(f"Invalid status '{v}' for ProductInfo")

    class Config:
        orm_mode = True
