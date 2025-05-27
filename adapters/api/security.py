# adapters/api/security.py
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import httpx
import config
from adapters.repositories.db_user_repository import DbUserRepository
from application_core.domain_models.user_model import User
from application_core.ports.user_repository_port import UserRepositoryPort
import asyncio
import logging

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer()
_jwks = None
_jwks_lock = asyncio.Lock()


async def _get_jwks_from_logto():
    global _jwks
    if _jwks is None:
        async with _jwks_lock:
            if _jwks is None:
                if not config.LOGTO_JWKS_URI:
                    logger.error("LOGTO_JWKS_URI no está configurado.")
                    raise ValueError("LOGTO_JWKS_URI no está configurado.")
                async with httpx.AsyncClient() as client:
                    try:
                        resp = await client.get(config.LOGTO_JWKS_URI, timeout=10)
                        resp.raise_for_status()
                        _jwks = resp.json()
                        logger.info("JWKS de Logto cargados exitosamente.")
                    except httpx.HTTPStatusError as e:
                        logger.error(
                            f"Error HTTP al obtener JWKS de Logto: {e.response.status_code} - {e.response.text}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="No se pudo obtener la clave de firma del proveedor de identidad.",
                        )
                    except Exception as e:
                        logger.error(
                            f"Error inesperado al obtener JWKS de Logto: {e}", exc_info=True
                        )
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Error al contactar al proveedor de identidad.",
                        )
    return _jwks


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    user_repo: UserRepositoryPort = Depends(lambda: DbUserRepository()),
) -> User:  # Devuelve tu modelo de dominio User
    token = credentials.credentials
    try:
        jwks = await _get_jwks_from_logto()
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise JWTError("Encabezado 'kid' faltante en el token.")

        public_key = {}
        for key_dict in jwks["keys"]:
            if key_dict["kid"] == kid:
                # No construir rsa_key manualmente para RSA.
                public_key = key_dict
                break

        if not public_key:
            raise JWTError(f"No se encontró la clave pública para el kid: {kid}")

        algorithm = unverified_header.get("alg", "ES384")

        payload = jwt.decode(
            token,
            public_key,
            algorithms=[algorithm],
            audience=config.LOGTO_AUDIENCE,
            issuer=config.LOGTO_ISSUER,
        )
    except JWTError as e:
        logger.warning(f"Error de validación de JWT: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido o expirado: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Error inesperado durante la decodificación del token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Error al procesar el token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    idp_id = payload.get("sub")
    if not idp_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token no contiene el identificador de usuario (sub).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await user_repo.get_by_idp_id(idp_id)
    if not user:
        username_from_token = payload.get("name") or payload.get("email") or idp_id
        new_user_domain_model = User(
            # id se genera automáticamente
            telegram_chat_id=None,  # No se conoce en este flujo de API
            idp_user_id=idp_id,
            username=username_from_token,
            is_active=True,
        )
        user = await user_repo.add(new_user_domain_model)
        if not user:
            logger.error(f"No se pudo crear el usuario en la BD para el idp_id: {idp_id}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al registrar el usuario.")
        logger.info(f"Nuevo usuario creado desde token JWT: {user.id} con idp_id {idp_id}")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo.")

    return user

