import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=150)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    is_verified: bool
    roles: list[str]

    @field_validator("roles", mode="before")
    @classmethod
    def serialize_roles(cls, roles: object) -> list[str]:
        return sorted(role.name for role in roles)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
