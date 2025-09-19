from http import HTTPStatus

from fastapi import (
    APIRouter, 
    WebSocket,
    WebSocketDisconnect
)

from lnbits.core.crud import get_user, update_payment, get_standalone_payment
from lnbits.core.models import WalletTypeInfo
from lnbits.decorators import (
    require_admin_key,
    require_invoice_key,
)
from lnbits.helpers import urlsafe_short_hash
from lnurl.exceptions import InvalidUrl
from lnurl.types import LnurlPayMetadata
from lnurl import encode as lnurl_encode

from lnbits.settings import settings
import httpx

from .crud import (
    get_device,
    create_partytap_payment,
    update_partytap_payment,
)


from loguru import logger

from lnbits.core.services import (
    websocket_manager,
    websocket_updater,
    create_invoice
)

from lnbits.core.models import (
    Payment
)

from lnbits.utils.exchange_rates import fiat_amount_as_satoshis


import json

from .models import Device, CreateDevice, Switch

partytap_ws_router = APIRouter(prefix="/api/v1/ws", tags = ["Websocket"])

async def websocket_send_switches(device: Device):
    message = {
        "event":"switches",
        "switches": [],
        "version": "865875",
        "branding": device.branding,
        "key":device.key        
    }
    for _switch in device.switches:
        message["switches"].append({
            "label": _switch.label,
            "id":  _switch.id,
            "duration": _switch.duration,
            "amount": _switch.amount,
            "currency": device.currency
        })

    await websocket_updater(device.id,json.dumps(message))

async def websocket_create_invoice(device: Device,switch: Switch):
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
        pin=""
    )

    if not partytap_payment:
        await websocket_updater(item_id,json.dumps({"status": "ERROR", "reason": "Could not create payment."}))
        return

    try:              
        memo = f"{device.title} {switch.label}"
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
                "id": partytap_payment.id,
                "received": False,
                "acknowledged": False,
                "fulfilled": False
            },
        )
        partytap_payment.payhash = payment.payment_hash
    except Exception as X:
        logger.error(f"An exception of type: {type(X).__name__} occured")
        logger.error(X)
        return
        
    await update_partytap_payment(partytap_payment)

    await websocket_updater(
        device.id,
        json.dumps({
            "event":"invoice",
            "pr": payment.bolt11,
            "payment_hash": payment.payment_hash
        })
    )

async def lnurl_withdraw(device: Device, payment_request: str,lnurlw: str):
    # validate lnurlw
    if not lnurlw.startswith("lnurlw://"):
        logger.error("lnurlw does not start with 'lnurlw://'")
        return

     # convert lnurlw into https URL
    url = 'https://' + lnurlw[9:]
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            result = response.json()
        except (httpx.ConnectError, httpx.RequestError):
            logger.error("http request failed")
            return

    if 'status' in result and result['status'] == "ERROR":
        logger.error("Error in LNURLW response")
        if 'reason' in result:
            logger.error(f"Reason: {result['reason']}")

        await websocket_updater(
            device.id,
            json.dumps({
                "event":"paymentfailed",
                "pr": payment_request
            })
        )

        return
    
    for field in ['k1','callback']:
        if not field in result:
            logger.error(f"No {field} in result")

            await websocket_updater(
                device.id,
                json.dumps({
                    "event":"paymentfailed",
                    "pr": payment_request
                })
            )
            
            return
    
    # construct callback url
    url = f"{result['callback']}?k1={result['k1']}&pr={payment_request}"
    
    # just make the call and forget about it 
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            result = response.json()
            logger.info(f"Payment response {result}")

            if 'status' in result and result['status'] == "ERROR":
                logger.error("Error in LNURLW response")
                if 'reason' in result:
                    logger.error(f"Reason: {result['reason']}")

                    
                await websocket_updater(
                    device.id,
                    json.dumps({
                        "event":"paymentfailed",
                        "pr": payment_request
                    })
                )

                return

            
        except (httpx.ConnectError, httpx.RequestError):
            logger.error("http request failed")

            await websocket_updater(
                device.id,
                json.dumps({
                    "event":"paymentfailed",
                    "pr": payment_request
                })
            )
            
            return

    # now the websocket should take it over from here

@partytap_ws_router.websocket("/{item_id}")
async def websocket_connect(websocket: WebSocket, item_id: str):

    logger.info("new connection")
    await websocket_manager.connect(websocket, item_id)

    device = await get_device(item_id)
    if not device:
        await websocket_updater(item_id,'{"event":"error","message":"device id does not exist"}')
        return
    

    await websocket_send_switches(device)

    try:    
        while settings.lnbits_running:
            message = await websocket.receive_text()

            logger.info(message)


            try:
                jsobj = json.loads(message)
            except json.decoder.JSONDecodeError:
                logger.warning("Invalid JSON message received. Ignoring")                                        
                continue
            
    
            if not "event" in jsobj:
                logger.warning("No event in message, ignored") 
                continue



            if jsobj["event"] == 'createinvoice':
                if not "switch_id" in jsobj:
                    logger.error(f"Required field: 'switch_id' not present in message")
                    continue

                switch = None
                for _switch in device.switches:
                    if _switch.id == jsobj["switch_id"]:
                        switch = _switch
                        break
                
                if not switch:
                    logger.error(f"No switch in device present with the current id")
                    continue

                await websocket_create_invoice(device,switch)

            elif jsobj["event"] in ["received","acknowledged","fulfilled"]:
                if not 'payment_hash' in jsobj:
                    logger.error("Required field: 'payment_hash' not present in message")
                    continue 
                try:    
                    payment = await get_standalone_payment(jsobj["payment_hash"])
                    if payment:
                        payment.extra[jsobj['event']] = True
                        await update_payment(payment)
                except TypeError as X:
                    logger.error(f"TypeError in call")
                    logger.error(X)
                    continue
                except Exception as X:
                    logger.error(f"An exception of type: {type(X).__name__} occured")
                    logger.error(X)
                    continue

            elif jsobj["event"] == "lnurlw":
                for field in ["payment_request","lnurlw"]:
                    if not field in jsobj:
                        logger.error(f"Required field: '{field}' not present in message")
                        continue
                try:
                    await lnurl_withdraw(device,jsobj["payment_request"],jsobj["lnurlw"])
                except Exception as X:
                    logger.error(f"An exception of type: {type(X).__name__} occured")
                    logger.error(X)
                    continue

            else:                
                logger.warning(f"Unknown event type {jsobj['event']} ignored")

    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)





