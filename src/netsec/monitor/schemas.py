"""Allowlisted input contracts; arbitrary headers and secrets are not accepted."""

import ipaddress
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Input):
    org_id: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

class NewUser(Input):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "analyst", "viewer"] = "viewer"

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
            raise ValueError("Valid email required")
        return value.lower()


class Setup(NewUser):
    organization: str = Field(min_length=1, max_length=100)


class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class UserUpdate(Input):
    role: Literal["admin", "analyst", "viewer"]
    active: bool


class SourceCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["app", "ssh"] = "app"


class Event(Input):
    event_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")
    timestamp: datetime
    event_type: Literal["auth.login", "password.change", "role.change"] = "auth.login"
    outcome: Literal["failure", "success"]
    source_ip: str = Field(max_length=45)
    username: str = Field(min_length=1, max_length=128)
    method: str = Field(default="password", min_length=1, max_length=40)
    host: str = Field(default="app", min_length=1, max_length=100)

    @field_validator("source_ip")
    @classmethod
    def valid_ip(cls, value):
        return str(ipaddress.ip_address(value))

    @field_validator("timestamp")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timestamp requires timezone")
        return value.astimezone(timezone.utc)

    @field_validator("username", "host", "method")
    @classmethod
    def no_controls(cls, value):
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Control characters are not accepted")
        return value


class Batch(Input):
    events: list[Event] = Field(min_length=1, max_length=200)


class IncidentUpdate(Input):
    version: int = Field(ge=1)
    status: Literal["open", "investigating", "resolved", "false_positive"]
    assignee_id: str | None = Field(default=None, max_length=64)


class CommentCreate(Input):
    body: str = Field(min_length=1, max_length=2000)


class PolicyUpdate(Input):
    threshold: int = Field(ge=2, le=100)
    window_seconds: int = Field(ge=10, le=3600)
    success_seconds: int = Field(ge=10, le=3600)
    notification_email: str = Field(default="", max_length=254)
    webhook_enabled: bool = False

    @field_validator("notification_email")
    @classmethod
    def email(cls, value):
        return NewUser.valid_email(value) if value else ""


class ExclusionCreate(Input):
    source_id: str = Field(min_length=1, max_length=64)
    cidr: str = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=1, max_length=200)
    expires_at: datetime

    @field_validator("cidr")
    @classmethod
    def network(cls, value):
        return str(ipaddress.ip_network(value, strict=False))

    @field_validator("expires_at")
    @classmethod
    def aware(cls, value):
        return Event.aware_time(value)
