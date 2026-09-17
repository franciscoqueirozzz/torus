"""API da plataforma Torus Meeting Intelligence."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.access import current_user, extract_token, manager_user, seller_for_user
from app.crm_routes import require_customer
from app.crm_routes import router as crm_router
from app.intent_classifier import get_model_metadata, load_model
from app.meeting_analysis import analyze_meeting
from app.storage import (
    authenticate_user,
    count_meetings,
    create_session,
    delete_session,
    get_meeting,
    get_user,
    init_db,
    list_meetings,
    list_sellers,
    save_meeting,
    save_message_analysis,
)
from app.text_processing import process_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = PROJECT_ROOT / "frontend" / "index.html"
MAX_UPLOAD_BYTES = 1_000_000


class LoginPayload(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=256)


class MessagePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    speaker: str = Field(
        default="unknown", min_length=1, max_length=80, examples=["cliente"]
    )
    text: str = Field(..., min_length=1, examples=["Estou pensando em cancelar."])


class MeetingPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    meeting_id: int = Field(..., examples=[101])
    title: str | None = Field(default=None, max_length=120)
    customer_name: str | None = Field(default=None, max_length=120)
    seller_id: int | None = None
    customer_id: int | None = None
    conversation: list[MessagePayload] = Field(..., min_length=1)


def _analyze_and_save(
    payload: dict[str, Any], user: dict[str, Any], requested_seller_id: int | None
) -> dict[str, Any]:
    if payload.get("customer_id") is not None:
        customer = require_customer(payload["customer_id"], user)
        seller_id = customer["seller_id"]
        payload["customer_name"] = customer["name"]
    else:
        seller_id = seller_for_user(user, requested_seller_id)
    result = analyze_meeting(payload)
    record_id = save_meeting(
        payload=payload,
        analysis=result,
        seller_id=seller_id,
        created_by=int(user["id"]),
    )
    result["record_id"] = record_id
    result["seller"] = get_user(seller_id)
    return result


def _seed_demo_meetings() -> None:
    if count_meetings() > 0:
        return
    manager = authenticate_user("manager@torus.ai", "Torus@2026")
    sellers = list_sellers()
    if manager is None or len(sellers) < 2:
        return
    seller_by_email = {seller["email"]: seller for seller in sellers}
    demos = (
        (
            seller_by_email["ana@torus.ai"]["id"],
            {
                "meeting_id": 301,
                "title": "Renovação ERP",
                "customer_name": "Grupo Horizonte",
                "conversation": [
                    {
                        "speaker": "vendedor",
                        "text": "Vamos revisar a renovação do Protheus.",
                    },
                    {
                        "speaker": "cliente",
                        "text": "O valor ficou muito alto para nosso orçamento.",
                    },
                    {
                        "speaker": "cliente",
                        "text": (
                            "Se não houver ajuste, podemos cancelar no próximo mês."
                        ),
                    },
                ],
            },
        ),
        (
            seller_by_email["ana@torus.ai"]["id"],
            {
                "meeting_id": 302,
                "title": "Expansão do Fluig",
                "customer_name": "Nova Energia",
                "conversation": [
                    {
                        "speaker": "vendedor",
                        "text": "Quais são os planos para as novas filiais?",
                    },
                    {
                        "speaker": "cliente",
                        "text": "Queremos expandir o Fluig e contratar mais licenças.",
                    },
                    {
                        "speaker": "cliente",
                        "text": "A equipe está satisfeita com o resultado.",
                    },
                ],
            },
        ),
        (
            seller_by_email["carlos@torus.ai"]["id"],
            {
                "meeting_id": 303,
                "title": "Acompanhamento do RM",
                "customer_name": "Alimentos Brasil",
                "conversation": [
                    {
                        "speaker": "vendedor",
                        "text": "Como está a operação depois da implantação?",
                    },
                    {
                        "speaker": "cliente",
                        "text": "O RM está funcionando muito bem para a equipe.",
                    },
                    {
                        "speaker": "cliente",
                        "text": "Os indicadores melhoraram bastante.",
                    },
                ],
            },
        ),
    )
    for seller_id, payload in demos:
        result = analyze_meeting(payload)
        save_meeting(payload, result, int(seller_id), int(manager["id"]))


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    _seed_demo_meetings()
    yield


app = FastAPI(
    title="Torus Meeting Intelligence",
    version="1.1.0",
    description="Análise de reuniões comerciais para vendedores e gerentes.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000", "null"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.mount("/assets", StaticFiles(directory=PROJECT_ROOT / "frontend"), name="assets")
app.include_router(crm_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    labels = {
        "name": "Nome",
        "email": "E-mail",
        "password": "Senha inicial",
        "new_password": "Nova senha",
        "current_password": "Senha atual",
        "title": "Título",
        "due_date": "Prazo",
        "customer_id": "Cliente",
        "conversation": "Falas da reunião",
        "text": "Texto da fala",
    }
    messages = []
    for error in exc.errors():
        field = labels.get(str(error["loc"][-1]), "Campo informado")
        kind = error["type"]
        context = error.get("ctx", {})
        if kind == "string_too_short":
            message = f"{field}: use pelo menos {context['min_length']} caracteres."
        elif kind == "string_too_long":
            message = f"{field}: use no máximo {context['max_length']} caracteres."
        elif kind == "value_error":
            message = str(context.get("error", "Confira o valor informado."))
        elif kind == "missing":
            message = f"{field}: preencha este campo."
        else:
            message = f"{field}: confira o formato ou a opção selecionada."
        if message not in messages:
            messages.append(message)
    return JSONResponse(status_code=422, content={"detail": " ".join(messages)})


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def dashboard() -> str:
    if not INDEX_PATH.exists():
        raise HTTPException(status_code=404, detail="Dashboard não encontrado.")
    return INDEX_PATH.read_text(encoding="utf-8")


@app.get("/health", tags=["Saúde"])
def healthcheck() -> dict[str, str]:
    try:
        model = load_model()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Modelo indisponível.") from exc
    if not isinstance(model, dict) or model.get("model_type") != "logistic_regression":
        raise HTTPException(status_code=503, detail="Modelo indisponível.")
    return {"status": "ok", "model": model["model_type"]}


@app.post("/auth/login", tags=["Autenticação"])
def login(payload: LoginPayload) -> dict[str, Any]:
    user = authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    return {
        "access_token": create_session(int(user["id"])),
        "token_type": "bearer",
        "user": user,
    }


@app.get("/auth/me", tags=["Autenticação"])
def auth_me(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
    return user


@app.post("/auth/logout", tags=["Autenticação"])
def logout(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict[str, bool]:
    token = extract_token(authorization)
    delete_session(token)
    return {"logged_out": True}


@app.get("/users/sellers", tags=["Equipe"])
def sellers(
    _: Annotated[dict[str, Any], Depends(manager_user)],
) -> list[dict[str, Any]]:
    return list_sellers()


@app.get("/meetings", tags=["Reuniões"])
def meetings(
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> list[dict[str, Any]]:
    return list_meetings(user)


@app.get("/meetings/{record_id}", tags=["Reuniões"])
def meeting_detail(
    record_id: int,
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> dict[str, Any]:
    record = get_meeting(record_id, user)
    if record is None:
        raise HTTPException(status_code=404, detail="Reunião não encontrada.")
    return record


@app.get("/model_metrics", tags=["Modelo"])
def model_metrics(
    _: Annotated[dict[str, Any], Depends(current_user)],
) -> dict[str, Any]:
    return get_model_metadata()


@app.post("/analyze", tags=["Análise"])
def analyze_message(
    payload: MessagePayload,
    _: Annotated[dict[str, Any], Depends(current_user)],
) -> dict[str, Any]:
    result = process_text(payload.model_dump())
    save_message_analysis(
        text=result["original_text"],
        intent=result["intent"],
        sentiment=result["sentiment"]["label"],
        churn_signal=result["features"]["churn_signal"],
    )
    return result


@app.post("/analyze_meeting", tags=["Análise"])
def analyze_complete_meeting(
    payload: MeetingPayload,
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> dict[str, Any]:
    values = payload.model_dump()
    return _analyze_and_save(values, user, payload.seller_id)


@app.post("/analyze_meeting_file", tags=["Análise"])
async def analyze_meeting_file(
    user: Annotated[dict[str, Any], Depends(current_user)],
    file: Annotated[UploadFile, File()],
    seller_id: Annotated[int | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
    customer_name: Annotated[str | None, Form()] = None,
    customer_id: Annotated[int | None, Form()] = None,
) -> dict[str, Any]:
    if not (file.filename or "").lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Envie um arquivo JSON válido.")
    try:
        file_content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(file_content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="O arquivo excede o limite de 1 MB.",
            )
        raw_payload = json.loads(file_content.decode("utf-8"))
        if not isinstance(raw_payload, dict):
            raise TypeError("A transcrição deve ser um objeto JSON.")
        if title:
            raw_payload["title"] = title
        if customer_name:
            raw_payload["customer_name"] = customer_name
        if seller_id is not None:
            raw_payload["seller_id"] = seller_id
        if customer_id is not None:
            raw_payload["customer_id"] = customer_id
        payload = MeetingPayload(**raw_payload)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        TypeError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail="JSON inválido ou fora do formato esperado.",
        ) from exc
    values = payload.model_dump()
    return _analyze_and_save(values, user, payload.seller_id)
