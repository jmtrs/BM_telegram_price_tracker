# application_core/domain_models/user_model.py
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

class User(BaseModel):
    id: UUID
    telegram_chat_id: Optional[int] = None
    idp_user_id: Optional[str] = None
    username: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

    class Config:
        orm_mode = True # Allows the model to be used with ORMs
