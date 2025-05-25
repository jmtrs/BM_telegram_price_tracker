# adapters/api/main.py
from fastapi import FastAPI, HTTPException, Depends, Query, Path, status
from typing import Optional, List
from uuid import UUID
import uvicorn
import logging

from . import schemas

# Application Core - Ports & Use Cases
from application_core.ports.alert_repository_port import AlertRepositoryPort
from application_core.ports.user_repository_port import UserRepositoryPort
from application_core.use_cases.user_use_cases import GetOrCreateUserByIdpIdUseCase
from application_core.use_cases.alert_use_cases import (
    CreateOrUpdateAlertUseCase,
    ListUserAlertsUseCase,
    DeleteAlertUseCase,
    GetProductInfoUseCase
)
from adapters.repositories.db_user_repository import DbUserRepository
from adapters.repositories.db_alert_repository import DbAlertRepository

# Database pool management for FastAPI app lifecycle
from db.connection import init_db_pool, close_db_pool

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Price Tracker API",
    description="API for managing product price tracking alerts.",
    version="0.1.0"
)

# --- FastAPI Lifecycle Events for DB Pool ---
@app.on_event("startup")
async def startup_event():
    await init_db_pool()
    logger.info("FastAPI application startup: DB pool initialized.")

@app.on_event("shutdown")
async def shutdown_event():
    await close_db_pool()
    logger.info("FastAPI application shutdown: DB pool closed.")

# --- Dependency Injection for Repositories ---
def get_user_repository() -> UserRepositoryPort:
    return DbUserRepository()

def get_alert_repository() -> AlertRepositoryPort:
    return DbAlertRepository()

# --- Health Check Endpoint ---
@app.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok"}

# --- Alert Endpoints ---
@app.post("/api/v1/alerts", response_model=schemas.AlertResponse, tags=["Alerts"])
async def create_or_update_alert_api(
    alert_data: schemas.AlertCreateRequest,
    user_repo: UserRepositoryPort = Depends(get_user_repository),
    alert_repo: AlertRepositoryPort = Depends(get_alert_repository)
):
    create_alert_use_case = CreateOrUpdateAlertUseCase(alert_repository=alert_repo, user_repository=user_repo)

    try:
        alert_record, scraped_info_schema, status_msg = await create_alert_use_case.execute(
            idp_user_id=alert_data.idp_user_id,
            url=alert_data.url,
            target_price=alert_data.target_price
        )

        return schemas.AlertResponse(
            id=alert_record['id'],
            chat_id=alert_record['chat_id'],
            full_url=alert_record['full_url'],
            clean_url=alert_record['clean_url'],
            target_price=alert_record['target_price'],
            status_message=status_msg,
            scraped_product_info=scraped_info_schema,
            inserted_at=alert_record['inserted_at'],
            last_price=alert_record.get('last_price'),
            last_notified=alert_record.get('last_notified')
        )
    except ValueError as e:
        logger.warning(f"Validation error in create_or_update_alert_api for {alert_data.idp_user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        logger.warning(f"Permission error in create_or_update_alert_api for {alert_data.idp_user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in create_or_update_alert_api for {alert_data.idp_user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while processing the alert.")

@app.get("/api/v1/alerts", response_model=schemas.UserAlertsResponse, tags=["Alerts"])
async def list_user_alerts_api(
    idp_user_id: str = Query(..., description="The identity provider user ID for whom to list alerts."),
    user_repo: UserRepositoryPort = Depends(get_user_repository),
    alert_repo: AlertRepositoryPort = Depends(get_alert_repository)
):
    list_alerts_use_case = ListUserAlertsUseCase(alert_repository=alert_repo, user_repository=user_repo)
    try:
        alert_records = await list_alerts_use_case.execute(idp_user_id=idp_user_id)
        alerts_for_response = [schemas.AlertDBRecord(**dict(record)) for record in alert_records]
        return schemas.UserAlertsResponse(alerts=alerts_for_response)
    except ValueError as e:
        logger.info(f"Could not list alerts for idp_user_id {idp_user_id}: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in list_user_alerts_api for idp_user_id {idp_user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while listing alerts.")

@app.delete("/api/v1/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Alerts"])
async def delete_alert_api(
    alert_id: UUID = Path(..., description="The ID of the alert to delete."),
    idp_user_id: str = Query(..., description="The identity provider user ID of the user owning the alert."),
    user_repo: UserRepositoryPort = Depends(get_user_repository),
    alert_repo: AlertRepositoryPort = Depends(get_alert_repository)
):
    delete_alert_use_case = DeleteAlertUseCase(alert_repository=alert_repo, user_repository=user_repo)
    try:
        success = await delete_alert_use_case.execute(idp_user_id=idp_user_id, alert_id_to_delete=alert_id)
        if not success:
            logger.warning(f"Alert {alert_id} for user {idp_user_id} was not deleted by use case.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found or could not be deleted based on the provided identifiers.")
        return
    except ValueError as e:
        logger.info(f"Could not delete alert {alert_id} for idp_user_id {idp_user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.warning(f"Forbidden attempt to delete alert {alert_id} by idp_user_id {idp_user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in delete_alert_api for alert {alert_id}, idp_user_id {idp_user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while deleting the alert.")

# --- Product Info Endpoint ---
@app.get("/api/v1/product-info", response_model=schemas.ScrapedProductInfo, tags=["Products"])
async def get_product_information_api(url: str):
    get_product_info_use_case = GetProductInfoUseCase()
    try:
        product_info_schema = await get_product_info_use_case.execute(url)
        return product_info_schema
    except ValueError as e:
        logger.info(f"Invalid URL for product info: {url}. Error: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in get_product_information_api for URL {url}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while fetching product info.")

# To run this API (from the project root directory):
# uvicorn adapters.api.main:app --reload
# You might need to adjust PYTHONPATH if imports are not found, e.g.:
# PYTHONPATH=. uvicorn adapters.api.main:app --reload
