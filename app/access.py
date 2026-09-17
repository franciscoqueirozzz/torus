"""Autenticação e autorização compartilhadas pelas rotas."""

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException

from app.storage import get_user, get_user_by_token


def extract_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Sua sessão expirou. Entre novamente."
        )
    return authorization.removeprefix("Bearer ").strip()


def current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict[str, Any]:
    user = get_user_by_token(extract_token(authorization))
    if user is None:
        raise HTTPException(
            status_code=401, detail="Sua sessão expirou. Entre novamente."
        )
    return user


def manager_user(user: Annotated[dict, Depends(current_user)]) -> dict:
    if user["role"] != "manager":
        raise HTTPException(
            status_code=403, detail="Esta área é exclusiva de gerentes."
        )
    return user


def seller_for_user(user: dict, requested_id: int | None) -> int:
    if user["role"] == "seller":
        return int(user["id"])
    seller = get_user(requested_id) if requested_id is not None else None
    if seller is None or seller["role"] != "seller":
        raise HTTPException(status_code=422, detail="Selecione um vendedor ativo.")
    return int(seller["id"])
