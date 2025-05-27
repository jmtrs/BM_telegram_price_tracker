# adapters/api/main.py
from fastapi import FastAPI, HTTPException, Depends, Query, Path, status, Request
from uuid import UUID
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
import logging
from starlette.middleware.sessions import SessionMiddleware

from . import schemas
from .security import get_current_user
from application_core.domain_models.user_model import User as UserModel

# Importaciones para Logto OIDC server-side flow
from .logto_auth import get_logto_client, get_signin_url, get_signout_url, LogtoClient, get_current_logto_session_user

# Application Core - Ports & Use Cases
from application_core.ports.alert_repository_port import AlertRepositoryPort
from application_core.ports.user_repository_port import UserRepositoryPort
from application_core.ports.scraped_price_repository_port import ScrapedPriceRepositoryPort

from application_core.use_cases.alert_use_cases import (
    CreateOrUpdateAlertUseCase,
    ListUserAlertsUseCase,
    DeleteAlertUseCase,
    GetProductInfoUseCase
)
from adapters.repositories.db_user_repository import DbUserRepository
from adapters.repositories.db_alert_repository import DbAlertRepository
from adapters.repositories.db_scraped_price_repository import DBScrapedPriceRepository

# Database pool management for FastAPI app lifecycle
from db.connection import init_db_pool, close_db_pool
import config

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Price Tracker API",
    description="API for managing product price tracking alerts.",
    version="0.1.0"
)

# Add SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET_KEY)


# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.on_event("startup")
async def startup_event():
    # Inicializar pool de BD
    await init_db_pool()
    logger.info("FastAPI application startup: DB pool initialized.")


@app.on_event("shutdown")
async def shutdown_event():
    # Cerrar pool de BD
    await close_db_pool()
    logger.info("FastAPI application shutdown: DB pool closed.")


# --- Dependency Injection for Repositories ---
def get_user_repository() -> UserRepositoryPort:
    return DbUserRepository()


def get_alert_repository() -> AlertRepositoryPort:
    return DbAlertRepository()

# ADDED: Dependency Injection for ScrapedPriceRepository
def get_scraped_price_repository() -> ScrapedPriceRepositoryPort:
    return DBScrapedPriceRepository()


# --- Health Check Endpoint ---
@app.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "ok"}


# --- Alert Endpoints ---
@app.post("/api/v1/alerts", response_model=schemas.AlertResponse, tags=["Alerts"])
async def create_or_update_alert_api(
        alert_data: schemas.AlertCreateRequest,
        current_api_user: UserModel = Depends(get_current_user),
        user_repo: UserRepositoryPort = Depends(get_user_repository),
        alert_repo: AlertRepositoryPort = Depends(get_alert_repository),
        scraped_price_repo: ScrapedPriceRepositoryPort = Depends(get_scraped_price_repository)
):
    create_alert_use_case = CreateOrUpdateAlertUseCase(
        alert_repository=alert_repo, 
        user_repository=user_repo,
        scraped_price_repository=scraped_price_repo
    )

    if not current_api_user.idp_user_id:
        logger.error(f"User {current_api_user.id} lacks idp_user_id.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User identification error.")

    try:
        alert_model, product_info_model, status_msg = await create_alert_use_case.execute(
            idp_user_id=current_api_user.idp_user_id,
            url=alert_data.url,
            target_price=alert_data.target_price
        )
        # Map domain ProductInfo to API schema
        scraped_info = schemas.ScrapedProductInfo(
            name=product_info_model.name,
            price=product_info_model.price,
            condition=product_info_model.product_condition,
            image=product_info_model.image_url,
            description=product_info_model.description,
            availability=product_info_model.availability,
            color=product_info_model.color,
            storage=product_info_model.storage,
            brand_name=product_info_model.brand_name,
            clean_url=str(product_info_model.clean_url),
            full_url=str(product_info_model.full_url),
            status=product_info_model.status
        )
        return schemas.AlertResponse(
            id=alert_model.id,
            full_url=str(alert_model.full_url),
            clean_url=str(alert_model.clean_url),
            target_price=alert_model.target_price,
            status_message=status_msg,
            scraped_product_info=scraped_info,
            inserted_at=alert_model.inserted_at,
            last_price=alert_model.last_price,
            last_notified=alert_model.last_notified
        )
    except ValueError as e:
        logger.warning(f"Validation error in create_or_update_alert_api for {current_api_user.idp_user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        logger.warning(f"Permission error in create_or_update_alert_api for {current_api_user.idp_user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in create_or_update_alert_api for {current_api_user.idp_user_id}: {e}",
                     exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="An unexpected error occurred while processing the alert.")


@app.get("/api/v1/alerts", response_model=schemas.UserAlertsResponse, tags=["Alerts"])
async def list_user_alerts_api(
        current_api_user: UserModel = Depends(get_current_user),
        user_repo: UserRepositoryPort = Depends(get_user_repository),
        alert_repo: AlertRepositoryPort = Depends(get_alert_repository)
):
    list_alerts_use_case = ListUserAlertsUseCase(alert_repository=alert_repo, user_repository=user_repo)
    if not current_api_user.idp_user_id:
        logger.error(f"User {current_api_user.id} lacks idp_user_id for listing alerts.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User identification error.")
    try:
        alerts = await list_alerts_use_case.execute(idp_user_id=current_api_user.idp_user_id)
        alerts_for_response = []
        for a in alerts:
            alerts_for_response.append(
                schemas.AlertDBRecord(
                    id=a.id,
                    user_id=a.user_id,
                    full_url=str(a.full_url),
                    clean_url=str(a.clean_url),
                    target_price=a.target_price,
                    last_price=a.last_price,
                    inserted_at=a.inserted_at,
                    last_notified=a.last_notified,
                    product_name=a.product_name
                )
            )
        return schemas.UserAlertsResponse(alerts=alerts_for_response)
    except ValueError as e:
        logger.info(f"Could not list alerts for idp_user_id {current_api_user.idp_user_id}: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in list_user_alerts_api for idp_user_id {current_api_user.idp_user_id}: {e}",
                     exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="An unexpected error occurred while listing alerts.")


@app.delete("/api/v1/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Alerts"])
async def delete_alert_api(
        alert_id: UUID = Path(..., description="The ID of the alert to delete."),
        current_api_user: UserModel = Depends(get_current_user),
        user_repo: UserRepositoryPort = Depends(get_user_repository),
        alert_repo: AlertRepositoryPort = Depends(get_alert_repository)
):
    delete_alert_use_case = DeleteAlertUseCase(alert_repository=alert_repo, user_repository=user_repo)
    if not current_api_user.idp_user_id:
        logger.error(f"User {current_api_user.id} lacks idp_user_id for deleting alert.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User identification error.")
    try:
        success = await delete_alert_use_case.execute(idp_user_id=current_api_user.idp_user_id, alert_id_to_delete=alert_id) # Usar idp_user_id
        if not success:
            logger.warning(f"Alert {alert_id} for user {current_api_user.sub} was not deleted by use case.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Alert not found or could not be deleted based on the provided identifiers.")
        return
    except ValueError as e:
        logger.info(f"Could not delete alert {alert_id} for idp_user_id {current_api_user.idp_user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.warning(f"Forbidden attempt to delete alert {alert_id} by idp_user_id {current_api_user.idp_user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(
            f"Unexpected error in delete_alert_api for alert {alert_id}, idp_user_id {current_api_user.idp_user_id}: {e}",
            exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="An unexpected error occurred while deleting the alert.")


# --- Product Info Endpoint ---
@limiter.limit("5/minute")
@app.get("/api/v1/product-info", response_model=schemas.ScrapedProductInfo, tags=["Products"])
async def get_product_information_api(request: Request, url: str):
    get_product_info_use_case = GetProductInfoUseCase()
    try:
        product_info_model = await get_product_info_use_case.execute(url)
        # Map domain ProductInfo to API schema
        return schemas.ScrapedProductInfo(
            name=product_info_model.name,
            price=product_info_model.price,
            condition=product_info_model.product_condition,
            image=product_info_model.image_url,
            description=product_info_model.description,
            availability=product_info_model.availability,
            color=product_info_model.color,
            storage=product_info_model.storage,
            brand_name=product_info_model.brand_name,
            clean_url=str(product_info_model.clean_url),
            full_url=str(product_info_model.full_url),
            status=product_info_model.status
        )
    except ValueError as e:
        logger.info(f"Invalid URL for product info: {url}. Error: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in get_product_information_api for URL {url}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="An unexpected error occurred while fetching product info.")


# --- User Info Endpoint (Protected by JWT) ---
@app.get("/api/v1/auth/me", response_model=schemas.UserResponse, tags=["Auth"])
async def read_users_me(current_api_user: UserModel = Depends(get_current_user)):
    """
    Devuelve la información del usuario autenticado actualmente (a través de JWT Bearer Token).
    """
    if not current_api_user.idp_user_id:
        logger.error(f"User object for JWT authenticated user {current_api_user.id} or {current_api_user.username} is missing idp_user_id.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User identification error in token data.")

    return schemas.UserResponse(
        id=current_api_user.id,
        idp_user_id=current_api_user.idp_user_id,
        username=current_api_user.username,
        is_active=current_api_user.is_active,
    )


# --- Logto Auth Endpoints ---
@app.get("/api/v1/auth/signin", tags=["Auth"])
async def sign_in(request: Request, client: LogtoClient = Depends(get_logto_client)):
    """
    Inicia el flujo de autenticación con Logto, redirigiendo al usuario a la página de inicio de sesión de Logto.
    """
    signin_url = await get_signin_url(client)
    return {"redirect_url": signin_url}


@app.get("/api/v1/auth/callback", tags=["Auth"])
async def auth_callback(
    request: Request,
    client: LogtoClient = Depends(get_logto_client),
    user_repo: UserRepositoryPort = Depends(get_user_repository)
):
    """
    Endpoint de callback que procesa la respuesta de Logto después de que el usuario se ha autenticado.
    """
    try:
        # Procesa la respuesta del callback
        await client.handleSignInCallback(str(request.url))
        
        # Obtener el Access Token para pruebas con API
        access_token = await client.getAccessToken(resource=config.LOGTO_AUDIENCE)
        logger.info(f"Access Token obtenido con resource='{config.LOGTO_AUDIENCE}'. Token (primeros 20 chars): {access_token[:20]}...")

        # Explícitamente obtener/crear el usuario en nuestra BD
        current_user = await get_current_logto_session_user(request=request, client=client, user_repo=user_repo)
        logger.info(f"Usuario procesado en callback. IDP ID: {current_user.idp_user_id}, Username: {current_user.username}, DB ID: {current_user.id}")
        
        id_token_claims = client.getIdTokenClaims()

        return {
            "status": "success", 
            "message": "Autenticación completada y usuario procesado.",
            "access_token": access_token, 
            "user_details": {
                "idp_user_id": current_user.idp_user_id,
                "username": current_user.username,
                "db_id": str(current_user.id) if current_user.id else None
            },
            "id_token_claims_for_debug": id_token_claims
        }
    except Exception as e:
        logger.error(f"Error en el callback de autenticación: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error en la autenticación: {str(e)}")


@app.get("/api/v1/auth/signout", tags=["Auth"])
async def sign_out(request: Request, client: LogtoClient = Depends(get_logto_client)):
    """
    Cierra la sesión del usuario con Logto.
    """
    signout_url = await get_signout_url(client)
    return {"redirect_url": signout_url}


@app.get("/api/v1/auth/me", response_model=UserModel, tags=["Auth"])
async def get_user_info(current_api_user: UserModel = Depends(get_current_user)):
    """
    Devuelve la información del usuario autenticado actualmente (basado en Bearer token).
    """
    return current_api_user

