from typing import Optional
from pydantic import BaseModel

class UserRegister(BaseModel):
    name: str
    email: str
    password: str
    user_type: str = "Organisation"
    organisation: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class UserOut(BaseModel):
    id: str
    name: str
    email: str
    user_type: str
    organisation: Optional[str] = None

    class Config:
        from_attributes = True
