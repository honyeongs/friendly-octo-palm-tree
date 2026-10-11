"""Narrow SaaS contracts, including explicit agreement and reauthentication."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from netsec.monitor.schemas import Input, NewUser, Setup, Event


class Signup(Setup):
    accepted_terms: Literal[True]
    terms_version: str = Field(min_length=1, max_length=80)


class EmailRequest(Input):
    org_id: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=254)

    _email = field_validator('email')(NewUser.valid_email.__func__)


class Consume(Input):
    token: str = Field(min_length=20, max_length=128)
    password: str = Field(default='', max_length=256)
    display_name: str = Field(default='', max_length=80)


class Invite(Input):
    email: str = Field(min_length=3, max_length=254)
    role: Literal['admin', 'analyst', 'viewer'] = 'viewer'
    _email = field_validator('email')(NewUser.valid_email.__func__)


class Reauth(Input):
    password: str = Field(min_length=1, max_length=256)


class Checkout(Reauth):
    plan: Literal['starter', 'team', 'business']


class MockConfirm(Reauth):
    request_id: str = Field(min_length=1, max_length=64)


class Integration(Reauth):
    webhook_url: str = Field(default='', max_length=2000)
    webhook_token: str | None = Field(default=None, max_length=512)
    oidc_issuer: str = Field(default='', max_length=500)
    oidc_client_id: str = Field(default='', max_length=200)
    oidc_client_secret: str | None = Field(default=None, max_length=512)
    oidc_require_mfa: bool = True
    sso_required: bool = False


class Due(Input):
    version: int = Field(ge=1)
    due_at: datetime
    ticket_ref: str = Field(default='', max_length=200)
    _time = field_validator('due_at')(Event.aware_time.__func__)


class PrivacyRequest(Reauth):
    kind: Literal['export', 'delete']
