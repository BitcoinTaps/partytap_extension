import asyncio
import json

from lnbits.core.models import Payment
from lnbits.core.services import (
    websocket_manager,
    websocket_updater
)
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import (
    get_device,
    get_partytap_payment,
    update_partytap_payment,
)


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_partytap")

    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


async def on_invoice_paid(payment: Payment) -> None:
    logger.info("Got Invoice")
    if payment.extra.get("tag") != "PartyTap":
        return

    logger.info("Got Partytap invoice")
    
    partytap_payment = await get_partytap_payment(payment.extra["id"])

    if not partytap_payment:
        return
    if partytap_payment.payhash == "paid":
        logger.info("paid")
        return
    if partytap_payment.payhash == "used":
        logger.info("used")
        return

    partytap_payment.payhash = payment.payment_hash
    partytap_payment = await update_partytap_payment(partytap_payment)

    message = json.dumps({
        'event':'paid',
        'payment_hash':partytap_payment.payhash,
        'payload':partytap_payment.payload
    })

    logger.info("sending on the socket")

    await websocket_updater(
        partytap_payment.deviceid,
        message
    )
        
