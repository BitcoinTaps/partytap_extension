from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Request
from lnbits.core.crud import get_user
from lnbits.core.models import WalletTypeInfo
from lnbits.decorators import (
    require_admin_key,
    require_invoice_key,
)
from lnbits.helpers import urlsafe_short_hash

from .crud import (
    create_device,
    delete_device,
    get_device,
    get_devices,
    update_device,
)
from .views_ws import (
    websocket_send_switches
)
from .views_lnurl import (
    lnurl_offline_payment
)
from lnbits.core.services import (
    websocket_manager
)
from .models import Device, CreateDevice, Switch

partytap_api_router = APIRouter()



@partytap_api_router.post(
    "/api/v1/partytap", dependencies=[Depends(require_admin_key)]
)
async def api_device_create(
    request: Request, data: CreateDevice
) -> Device:

    device_id = urlsafe_short_hash()[:8]

    # create id for each switch
    for switch in data.switches:
        switch.id = urlsafe_short_hash()[:8]
    
    return await create_device(device_id, data)


@partytap_api_router.put(
    "/api/v1/partytap/{device_id}",
    dependencies=[Depends(require_admin_key)],
)
async def api_device_update(
    request: Request, data: CreateDevice, device_id: str
):
    device = await get_device(device_id)
    if not device:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="partytap device does not exist"
        )

    for k, v in data.dict().items():
        if v is not None:
            setattr(device, k, v)

    device.switches = data.switches

    device = await update_device(device)

    await websocket_send_switches(device)

    return device

@partytap_api_router.get("/api/v1/partytap")
async def api_devices_retrieve(
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Device]:
    user = await get_user(key_info.wallet.user)
    assert user, "partytap cannot retrieve user"
    devices = await get_devices(user.wallet_ids)
    for device in devices:
        device.websocket = 0
        for connection in websocket_manager.active_connections:
            if connection.path_params["item_id"] == device.id:
                device.websocket += 1
    return devices


@partytap_api_router.get(
    "/api/v1/partytap/{device_id}",
    dependencies=[Depends(require_invoice_key)],
)
async def api_device_retrieve(device_id: str):
    device = await get_device(device_id)
    if not device:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="partytap device does not exist"
        )

    device.websocket = 0
    for connection in websocket_manager.active_connections:
        if connection.path_params["item_id"] == device.id:
            device.websocket += 1

    return device


@partytap_api_router.delete(
    "/api/v1/partytap/{device_id}",
    dependencies=[Depends(require_admin_key)],
)
async def api_device_delete(device_id: str):
    device = await get_device(device_id)
    if not device:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="partytap device does not exist."
        )
    await delete_device(device_id)

@partytap_api_router.get(
    "/api/v1/device/{device_id}/payment"
)
async def api_lnurldevice_offline_payment(req: Request, device_id: str, encrypted: str, iv: str):
    return await lnurl_offline_payment(req, device_id, encrypted, iv)
