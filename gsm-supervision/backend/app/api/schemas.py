"""Schémas Pydantic partagés par les routes."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["ADMIN", "SUPERVISOR", "VIEWER"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str | None
    role: Role
    can_export: bool
    is_active: bool
    must_change_password: bool
    failed_logins: int
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    must_change_password: bool
    user: UserOut


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
    full_name: str | None = Field(default=None, max_length=200)
    password: str = Field(min_length=1, max_length=200)
    role: Role = "VIEWER"
    can_export: bool = False


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    role: Role | None = None
    can_export: bool | None = None
    is_active: bool | None = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=1, max_length=200)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    at: datetime
    user_id: int | None
    username: str | None
    action: str
    target: str | None
    details: dict
    ip: str | None


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
