from http import HTTPStatus

from fastapi import APIRouter, Query, Request, HTTPException
from lnbits.core.services import create_invoice
from lnbits.utils.exchange_rates import fiat_amount_as_satoshis
import json
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from hashlib import sha256
from loguru import logger
import json

from pydantic import parse_obj_as


from lnurl import LnurlErrorResponse, LnurlPayActionResponse, LnurlPayResponse
from lnurl.models import UrlAction
from lnurl.types import (
    ClearnetUrl,
    DebugUrl,
    LightningInvoice,
    Max144Str,
    MilliSatoshi,
    OnionUrl,
    LnurlPayMetadata,
)

from .crud import (
    get_device,
    create_partytap_payment,
    update_partytap_payment,
    get_partytap_payment
)

partytap_lnurl_router = APIRouter(prefix="/api/v1/lnurl")


@partytap_lnurl_router.get(
    "/{device_id}",
    status_code=HTTPStatus.OK,
    name="partytap.lnurl_params",
)
async def lnurl_offline_payment(
    request: Request,
    device_id: str,
    encrypted: str,
    iv: str
): 
    logger.info("Entered lnurl_offline_payment")
    device = await get_device(device_id)
    if not device:
        return {
            "status": "ERROR",
            "reason": f"partytap device {device_id} not found on this server",
        }

    # convert IV to byte string
    ivBytes = bytes.fromhex(iv)
    keyBytes = str.encode(device.key[:16])
    encryptedBytes = bytes.fromhex(encrypted)

    # we're using AES CBC mode
    cipher = Cipher(algorithms.AES(keyBytes), modes.CBC(ivBytes))
    decryptor = cipher.decryptor()
    decrypted_message = decryptor.update(encryptedBytes) + decryptor.finalize()

    if ( decrypted_message[16:].hex() != sha256(decrypted_message[:16]).hexdigest() ):
        logger.info(f"Incorrect message hash, message ignored")
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Incorrect input"
        )


    # Check they're not trying to trick the switch!
    switch_id = decrypted_message[0:8].decode()
    switch = None
    for _switch in device.switches:
        if _switch.id == switch_id:
            switch = _switch
            break
    if not switch:
        return {"status": "ERROR", "reason": "Switch params wrong"}
    

    # extract PIN
    # e = 'b'Lfzmmibg:961:\x00\xfe?!\xf9\xabl
    decrypted_pin_part = decrypted_message[9:13].decode()
    result = decrypted_pin_part.find(':')
    if result == -1:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Incorrect payload"
        )
    secret_pin = decrypted_pin_part[:result]

    # determine price
    price_msat = int(
        (
            await fiat_amount_as_satoshis(float(switch.amount), device.currency)
            if device.currency != "sat"
            else float(switch.amount)
        ) 
        * 1000
    )

    partytap_payment = await create_partytap_payment(
        device_id=device.id,
        switch_id=switch.id,
        payload=switch.duration,
        amount_msat=price_msat,
        payment_hash="not yet set",
        pin=secret_pin
    )
    if not partytap_payment:
        return {"status": "ERROR", "reason": "Could not create payment."}

    url = str(
        request.url_for(
            "partytap.lnurl_callback", payment_id=partytap_payment.id
        )
    )

    memo = f"{device.title} {switch.label}"
    resp =  LnurlPayResponse(
        callback=url,
        minSendable=MilliSatoshi(price_msat),
        maxSendable=MilliSatoshi(price_msat),
        metadata=LnurlPayMetadata(json.dumps([["text/plain", memo]])),
    )
    return resp.dict()


@partytap_lnurl_router.get(
    "/cb/{payment_id}",
    status_code=HTTPStatus.OK,
    name="partytap.lnurl_callback",
)
async def lnurl_callback( 
    request: Request,
    payment_id: str,
    pr: int = Query(None),
    k1: str = Query(None),
):
    logger.info("Entered lnurl_callback")
    partytap_payment = await get_partytap_payment(payment_id)
    if not partytap_payment:
        return LnurlErrorResponse(reason = "partytap payment not found.")
    device = await get_device(partytap_payment.deviceid)
    if not device:
        return LnurlErrorResponse(reason = "device not found.")

    switch = None
    for _switch in device.switches:
        if _switch.id == partytap_payment.switchid:
            switch = _switch
            break
    
    if not switch:
        return LnurlErrorResponse(reason = "device switch not found.")

    memo = f"{device.title} {switch.label}"
    try:
        payment = await create_invoice(
            wallet_id=device.wallet,
            amount=int(partytap_payment.sats / 1000),
            memo=memo,
            unhashed_description=LnurlPayMetadata(json.dumps([["text/plain", memo]])).encode(),
            extra={
                "tag": "PartyTap",
                "Device": device.id,
                "Switch": switch.id,
                "amount": switch.amount,
                "currency": device.currency,
                "id": payment_id,
                "received": False,
                "acknowledged": False,
                "fulfilled": False,
                "offline": True
            },
        )
    except Exception as X:
        logger.error(f"An exception of type: {type(X).__name__} occured")
        logger.error(X)
        return LnurlErrorResponse(reason = "Failed to create invoice")

    partytap_payment.payhash = payment.payment_hash
    await update_partytap_payment(partytap_payment)

    if ( partytap_payment.pin is not None and len(partytap_payment.pin) > 0 ):
        logger.info("PIN is defined")
        url = str(request.url_for("partytap.displaypin", paymentid=payment_id))

        succes_action = UrlAction(
            url=url,
            description=Max144Str(
                "Open to get the confirmation PIN."
            ),
        )
        invoice = parse_obj_as(LightningInvoice,LightningInvoice(payment.bolt11))
        resp = LnurlPayActionResponse(
            pr=invoice,
            successAction=succes_action,
            routes=[]
        )

        return resp.dict()
    else:
        logger.info("PIN is not defined")
        return LnurlErrorResponse(reason = "No PIN defined")