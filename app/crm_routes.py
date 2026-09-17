"""Rotas para clientes, tarefas e administração de acesso."""

import csv
import io
import re
import sqlite3
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import crm, storage
from app.access import current_user, manager_user, seller_for_user

router = APIRouter()
User = Annotated[dict, Depends(current_user)]
Manager = Annotated[dict, Depends(manager_user)]


class CustomerValues(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    segment: str = Field(default="", max_length=100)
    stage: Literal["prospect", "active", "renewal", "inactive"] = "active"
    notes: str = Field(default="", max_length=4000)


class CustomerCreate(CustomerValues):
    seller_id: int | None = None


class TaskValues(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    due_date: date
    priority: Literal["normal", "high"] = "normal"
    notes: str = Field(default="", max_length=4000)


class TaskCreate(TaskValues):
    customer_id: int
    meeting_id: int | None = None


class TaskUpdate(TaskValues):
    status: Literal["open", "done"]


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254)
    password: str = Field(min_length=15, max_length=128)
    role: Literal["seller", "manager"] = "seller"
    current_password: str = Field(min_length=1, max_length=256)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Informe o nome da pessoa.")
        return value.strip()

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Informe um e-mail válido, como nome@empresa.com.")
        return value


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=15, max_length=128)


class AccessChange(BaseModel):
    active: bool
    current_password: str = Field(min_length=1, max_length=256)


class MeetingEdit(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)


def require_customer(customer_id: int, user: dict) -> dict:
    customer = crm.get_customer(customer_id, user)
    if customer is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return customer


def confirm_manager_password(user: dict, password: str) -> None:
    if storage.authenticate_user(user["email"], password) is None:
        raise HTTPException(status_code=400, detail="Confira sua senha atual.")


@router.get("/customers", tags=["Clientes"])
def customers(user: User):
    return crm.list_customers(user)


@router.post("/customers", status_code=201, tags=["Clientes"])
def add_customer(payload: CustomerCreate, user: User):
    seller_id = seller_for_user(user, payload.seller_id)
    try:
        customer_id = crm.create_customer(payload.model_dump(), seller_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            409, "Já existe um cliente com esse nome nessa carteira."
        ) from exc
    return require_customer(customer_id, user)


@router.get("/customers/{customer_id}", tags=["Clientes"])
def customer_detail(customer_id: int, user: User):
    customer = require_customer(customer_id, user)
    customer["meetings"] = [
        item
        for item in storage.list_meetings(user)
        if item["customer_id"] == customer_id
    ]
    customer["tasks"] = [
        item for item in crm.list_tasks(user) if item["customer_id"] == customer_id
    ]
    return customer


@router.patch("/customers/{customer_id}", tags=["Clientes"])
def edit_customer(customer_id: int, payload: CustomerValues, user: User):
    require_customer(customer_id, user)
    try:
        crm.update_customer(customer_id, payload.model_dump(), user)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            409, "Já existe um cliente com esse nome nessa carteira."
        ) from exc
    return require_customer(customer_id, user)


@router.get("/tasks", tags=["Acompanhamento"])
def tasks(user: User):
    return crm.list_tasks(user)


@router.post("/tasks", status_code=201, tags=["Acompanhamento"])
def add_task(payload: TaskCreate, user: User):
    require_customer(payload.customer_id, user)
    if payload.meeting_id is not None:
        meeting = storage.get_meeting(payload.meeting_id, user)
        if meeting is None or meeting["customer_id"] != payload.customer_id:
            raise HTTPException(422, "Selecione uma reunião desse cliente.")
    task_id = crm.create_task(payload.model_dump(), user)
    return next(item for item in crm.list_tasks(user) if item["id"] == task_id)


@router.patch("/tasks/{task_id}", tags=["Acompanhamento"])
def edit_task(task_id: int, payload: TaskUpdate, user: User):
    if not crm.update_task(task_id, payload.model_dump(), user):
        raise HTTPException(404, "Tarefa não encontrada.")
    return next(item for item in crm.list_tasks(user) if item["id"] == task_id)


@router.patch("/meetings/{record_id}", tags=["Reuniões"])
def edit_meeting(record_id: int, payload: MeetingEdit, user: User):
    if not storage.rename_meeting(record_id, payload.title, user):
        raise HTTPException(404, "Reunião não encontrada.")
    return storage.get_meeting(record_id, user)


@router.get("/users", tags=["Equipe"])
def users(user: Manager):
    return storage.list_users()


@router.post("/users", status_code=201, tags=["Equipe"])
def add_user(payload: UserCreate, user: Manager):
    confirm_manager_password(user, payload.current_password)
    try:
        user_id = storage.create_user(
            payload.name, payload.email, payload.password, payload.role
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Este e-mail já está cadastrado na equipe.") from exc
    return storage.get_user(user_id)


@router.patch("/users/{user_id}/access", tags=["Equipe"])
def edit_access(user_id: int, payload: AccessChange, user: Manager):
    confirm_manager_password(user, payload.current_password)
    if user_id == user["id"]:
        raise HTTPException(422, "Você não pode desativar seu próprio acesso.")
    if not storage.set_user_active(user_id, payload.active):
        raise HTTPException(404, "Usuário não encontrado.")
    return {"id": user_id, "active": payload.active}


@router.post("/auth/change-password", tags=["Autenticação"])
def update_password(payload: PasswordChange, user: User):
    if payload.current_password == payload.new_password:
        raise HTTPException(422, "Escolha uma senha diferente da atual.")
    if not storage.change_password(
        user["id"], payload.current_password, payload.new_password
    ):
        raise HTTPException(400, "Confira sua senha atual.")
    return {"message": "Senha alterada. Entre novamente com a nova senha."}


def safe_csv(value: object) -> str:
    text = str(value if value is not None else "")
    # Evita fórmulas executáveis quando a planilha abre textos fornecidos por usuários.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + text
    return text


@router.get("/reports/meetings.csv", tags=["Relatórios"])
def meeting_report(user: User):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "Registro",
            "Cliente",
            "Reunião",
            "Vendedor",
            "Data de registro",
            "Risco (0-100)",
            "Oportunidade (0-100)",
            "Próxima ação sugerida",
        ]
    )
    for item in storage.list_meetings(user):
        summary = item["summary"]
        writer.writerow(
            map(
                safe_csv,
                [
                    item["id"],
                    item["customer_name"],
                    item["title"],
                    item["seller"]["name"],
                    item["created_at"],
                    summary["churn_risk_score"],
                    summary["opportunity_score"],
                    summary["recommended_action"],
                ],
            )
        )
    return Response(
        "\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="torus-reunioes.csv"'},
    )
