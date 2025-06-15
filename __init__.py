import asyncio

from fastapi import APIRouter
from loguru import logger

from .crud import db
from .tasks import wait_for_paid_invoices
from .views import partytap_generic_router
from .views_api import partytap_api_router
from .views_lnurl import partytap_lnurl_router
from .views_ws import partytap_ws_router

partytap_ext: APIRouter = APIRouter(
    prefix="/partytap", tags=["partytap"]
)
partytap_ext.include_router(partytap_generic_router)
partytap_ext.include_router(partytap_api_router)
partytap_ext.include_router(partytap_lnurl_router)
partytap_ext.include_router(partytap_ws_router)

partytap_static_files = [
    {
        "path": "/partytap/static",
        "name": "partytap_static",
    }
]
scheduled_tasks: list[asyncio.Task] = []


def partytap_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def partytap_start():
    from lnbits.tasks import create_permanent_unique_task

    task = create_permanent_unique_task("ext_partytap", wait_for_paid_invoices)
    scheduled_tasks.append(task)
    logger.info("Added scheduled task")

__all__ = [
    "db",
    "partytap_ext",
    "partytap_static_files",
    "partytap_start",
    "partytap_stop",
]
