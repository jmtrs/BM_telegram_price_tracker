# application_core/domain_models/user_model.py
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel, Field


class User(BaseModel):
    id: UUID = Field(default_factory=uuid4) # Asignar un UUID por defecto si no se provee
    telegram_chat_id: Optional[int] = None
    idp_user_id: Optional[str] = None # Identificador del proveedor de identidad (Logto sub)
    username: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

    class Config:
        orm_mode = True
