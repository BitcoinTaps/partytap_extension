from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from http import HTTPStatus
from lnbits.core.crud import get_standalone_payment

from .crud import (
    create_partytap_payment,
    get_device,
    get_partytap_payment,
    update_partytap_payment,
)
from loguru import logger

partytap_generic_router = APIRouter()


def partytap_renderer():
    return template_renderer(["partytap/templates"])


@partytap_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return partytap_renderer().TemplateResponse(
        "partytap/index.html",
        {"request": request, "user": user.json()}
    )

@partytap_generic_router.get(
    "/{paymentid}", name="partytap.displaypin", response_class=HTMLResponse
)
async def displaypin(request: Request, paymentid: str):
    partytap_payment = await get_partytap_payment(paymentid)
    if not partytap_payment:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="No payment"
        )
    logger.info("Got partytap_payment")
    payment = await get_standalone_payment(partytap_payment.payhash)
    logger.info("Got payme")
    if not payment:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Payment not found."
        )
    status = await payment.check_status()
    if status.success:
        return partytap_renderer().TemplateResponse(
            "partytap/paid.html", {"request": request, "pin": partytap_payment.pin}
        )
    
    return partytap_renderer().TemplateResponse(
        "partytap/notpaid.html",
        {"request": request},
    )
    

