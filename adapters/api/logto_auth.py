# adapters/api/logto_auth.py
import logging
from typing import Optional, Union
from fastapi import Request, Depends, HTTPException, status
from logto import LogtoClient, LogtoConfig, Storage
from pydantic import BaseModel
import config
from application_core.domain_models.user_model import User
from application_core.ports.user_repository_port import UserRepositoryPort
from adapters.repositories.db_user_repository import DbUserRepository

logger = logging.getLogger(__name__)


# Define el modelo de información de usuario de Logto
class UserInfo(BaseModel):
    sub: str  # Este es el idp_user_id
    name: Optional[str] = None
    email: Optional[str] = None
    picture: Optional[str] = None


# URLs de callback para autenticación
SIGN_IN_CALLBACK = "/api/v1/auth/callback"
BASE_URL = "http://localhost:8000"


# Implementación de almacenamiento para FastAPI
class FastAPISessionStorage(Storage):
    def __init__(self, request: Request):
        self.request = request
        if not hasattr(request, 'session'):
            raise RuntimeError("SessionMiddleware no está configurada o la sesión no está disponible en la solicitud.")
        self.session = request.session

    def get(self, key: str) -> Union[str, None]:
        return self.session.get(key, None)

    def set(self, key: str, value: Union[str, None]) -> None:
        self.session[key] = value

    def delete(self, key: str) -> None:
        if key in self.session:
            del self.session[key]


# Inicialización del cliente Logto
def get_logto_client(request: Request):  # request es necesario para FastAPISessionStorage
    return LogtoClient(
        LogtoConfig(
            endpoint=config.LOGTO_ENDPOINT,
            appId=config.LOGTO_APP_ID,
            appSecret=config.LOGTO_APP_SECRET,
            audiences=[config.LOGTO_AUDIENCE],
            scopes=['openid', 'profile', 'email', 'offline_access']
        ),
        storage=FastAPISessionStorage(request)
    )


# Dependencia para obtener el usuario actual de Logto (usando el flujo de sesión/cookie de LogtoClient)
async def get_current_logto_session_user(
        request: Request,
        client: LogtoClient = Depends(get_logto_client),
        user_repo: UserRepositoryPort = Depends(lambda: DbUserRepository())
) -> User:  # Devuelve tu modelo de dominio User
    try:
        if not client.isAuthenticated():  # Esto verifica la sesión de Logto
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No autenticado vía sesión Logto"
            )

        logto_claims = client.getIdTokenClaims()  # Obtiene claims del ID token de la sesión

        idp_id = logto_claims.sub
        if not idp_id:
            logger.error("Logto ID token no contiene 'sub' claim.")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Claim 'sub' faltante en token de Logto")

        user = await user_repo.get_by_idp_id(idp_id)
        if not user:
            # Crear nuevo usuario si no existe en tu BD
            username_from_logto = logto_claims.name or logto_claims.email or idp_id
            new_user_domain_model = User(
                telegram_chat_id=None,
                idp_user_id=idp_id,
                username=username_from_logto,
                is_active=True
            )
            user = await user_repo.add(new_user_domain_model)
            if not user:
                logger.error(f"No se pudo crear el usuario para el idp_id de Logto: {idp_id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error al crear el usuario en la base de datos"
                )
            logger.info(f"Nuevo usuario creado desde Logto: {user.id} con idp_id {idp_id}")

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inactivo"
            )
        return user

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error inesperado en get_current_logto_session_user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor durante la autenticación de sesión"
        )


# Helper para verificar autenticación sin requerir datos del usuario
async def is_authenticated(
        request: Request,
        client: LogtoClient = Depends(get_logto_client)
) -> bool:
    return await client.isAuthenticated()


# Helper para crear URLs de autenticación
async def get_signin_url(client: LogtoClient):
    return await client.signIn(redirectUri=f"{BASE_URL}{SIGN_IN_CALLBACK}")


async def get_signout_url(client: LogtoClient):
    return await client.signOut(postLogoutRedirectUri=BASE_URL)
