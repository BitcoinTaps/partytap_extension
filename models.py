import json
from datetime import datetime, timezone
from typing import Optional

from lnurl import encode as lnurl_encode
from lnurl.types import LnurlPayMetadata
from pydantic import BaseModel, Field, Extra

class Switch(BaseModel):
    id: Optional[str]
    amount: float = 0.0
    duration: int = 0
    label: Optional[str]
    lnurl: str = ""

class CreateDevice(BaseModel):
    title: str
    wallet: str
    currency: str
    branding: str
    switches: list[Switch]

class Device(BaseModel, extra=Extra.allow):
    id: str
    key: str
    title: str
    wallet: str
    currency: str
    branding: str
    switches: list[Switch]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PartytapPayment(BaseModel):
    id: str
    deviceid: str
    payhash: str
    switchid: str
    payload: str
    pin: str
    sats: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
