from datetime import datetime, timezone
from typing import Optional

import shortuuid
import time
from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash
from sqlalchemy.exc import OperationalError


from .models import (
    Device,
    PartytapPayment,
    CreateDevice,
)

from loguru import logger
import json

db = Database("ext_partytap")


async def create_device(
    device_id: str,
    data: CreateDevice,
) -> Device:
    device_key = urlsafe_short_hash()
    device = Device(
        id=device_id,
        key=device_key,
        title=data.title,
        wallet=data.wallet,
        currency=data.currency,
        branding=data.branding,
        switches=data.switches
    )
    await db.insert("partytap.device", device)
    return device


async def update_device(device: Device) -> Device:
    await db.update("partytap.device", device)
    return device


async def get_device(device_id: str) -> Optional[Device]:
    return await db.fetchone(
        "SELECT * FROM partytap.device WHERE id = :id",
        {"id": device_id},
        Device,
    )


async def get_devices(wallet_ids: list[str]) -> list[Device]:
    q = ",".join([f"'{w}'" for w in wallet_ids])
    return await db.fetchall(
        f"""
        SELECT * FROM partytap.device WHERE wallet IN ({q})
        ORDER BY id
        """,
        model=Device,
    )


async def delete_device(device_id: str) -> None:
    await db.execute(
        "DELETE FROM partytap.device WHERE id = :id",
        {"id": device_id},
    )


async def create_partytap_payment(
    device_id: str,
    switch_id: str,
    payment_hash: str,
    payload: str,
    amount_msat: int,
    pin: str
) -> PartytapPayment:
    payment_id = urlsafe_short_hash()
    payment = PartytapPayment(
        id=payment_id,
        deviceid=device_id,
        switchid=switch_id,
        payload=payload,
        pin=pin,
        payhash=payment_hash,
        sats=amount_msat
    )

    try: 
        await db.insert("partytap.payment", payment)
    except OperationalError as X:
        logger.info(X)
        raise
    except Exception as X:
        logger.info(X)
        raise

    return payment


async def update_partytap_payment(
    payment: PartytapPayment,
) -> PartytapPayment:
    try:
        await db.update("partytap.payment", payment)
    except OperationalError as X:
        logger.error(f"SQL Error: {X}")
        raise
    except Exception as X:
        logger.error(f"An exception of type: {type(X).__name__} occured")
        raise
    return payment
    


async def delete_partytap_payment(payment_id: str) -> None:
    await db.execute(
        "DELETE FROM partytap.payment WHERE id = :id",
        {"id": payment_id},
    )


async def get_partytap_payment(
    payment_id: str,
) -> Optional[PartytapPayment]:
    return await db.fetchone(
        "SELECT * FROM partytap.payment WHERE id = :id",
        {"id": payment_id},
        PartytapPayment,
    )


async def get_partytap_payments(
    device_ids: list[str],
) -> list[PartytapPayment]:
    if len(device_ids) == 0:
        return []
    q = ",".join([f"'{w}'" for w in device_ids])
    return await db.fetchall(
        f"""
        SELECT * FROM partytap.payment WHERE deviceid IN ({q})
        ORDER BY id
        """,
        model=PartytapPayment,
    )


async def get_partytap_payment_by_payhash(
    payhash: str,
) -> Optional[PartytapPayment]:
    return await db.fetchone(
        "SELECT * FROM partytap.payment WHERE payhash = :payhash",
        {"payhash": payhash},
    )


async def get_partytap_payment_by_payload(
    payload: str,
) -> Optional[PartytapPayment]:
    return await db.fetchone(
        "SELECT * FROM partytap.payment WHERE payload = :payload",
        {"payload": payload},
        PartytapPayment,
    )


async def get_recent_partytap_payment(
    deviceid: str,
    delay: int
) -> Optional[PartytapPayment]:
    return await db.fetchone(
        """
        SELECT * FROM partytap.payment
        WHERE deviceid = :deviceid WHERE timestamp > {query_timestamp} ORDER BY timestamp DESC LIMIT 1
        """,
        {
            "deviceid": deviceid,
            "query_timestamp": db.timestamp_now - delay
        },        
        PartytapPayment,
    )
