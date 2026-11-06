from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, StringConstraints

from apps.api.db import get_connection

router = APIRouter(prefix="/api/v1/companies", tags=["organizations"])
Connection = Annotated[psycopg.Connection, Depends(get_connection, scope="function")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


class CompanyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name


class Company(CompanyInput):
    id: UUID
    created_at: datetime


class EmployeeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: Name


class Employee(EmployeeInput):
    id: UUID
    company_id: UUID
    created_at: datetime


def require_company(connection: psycopg.Connection, company_id: UUID) -> None:
    if not connection.execute("SELECT id FROM companies WHERE id = %s", (company_id,)).fetchone():
        raise HTTPException(404, "Компания не найдена")


@router.get("", response_model=list[Company])
def list_companies(connection: Connection, limit: Limit = 100, offset: Offset = 0):
    return connection.execute(
        "SELECT * FROM companies ORDER BY created_at, id LIMIT %s OFFSET %s", (limit, offset)
    ).fetchall()


@router.post("", response_model=Company, status_code=201)
def create_company(data: CompanyInput, connection: Connection):
    return connection.execute(
        "INSERT INTO companies (id, name) VALUES (%s, %s) RETURNING *", (uuid4(), data.name)
    ).fetchone()


@router.put("/{company_id}", response_model=Company)
def update_company(company_id: UUID, data: CompanyInput, connection: Connection):
    company = connection.execute(
        "UPDATE companies SET name = %s WHERE id = %s RETURNING *", (data.name, company_id)
    ).fetchone()
    if company is None:
        raise HTTPException(404, "Компания не найдена")
    return company


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: UUID, connection: Connection):
    try:
        result = connection.execute("DELETE FROM companies WHERE id = %s", (company_id,))
    except psycopg.errors.ForeignKeyViolation as error:
        raise HTTPException(409, "Компания связана с сотрудниками или звонками") from error
    if result.rowcount == 0:
        raise HTTPException(404, "Компания не найдена")
    return Response(status_code=204)


@router.get("/{company_id}/employees", response_model=list[Employee])
def list_employees(
    company_id: UUID, connection: Connection, limit: Limit = 100, offset: Offset = 0
):
    require_company(connection, company_id)
    return connection.execute(
        "SELECT * FROM employees WHERE company_id = %s ORDER BY created_at, id LIMIT %s OFFSET %s",
        (company_id, limit, offset),
    ).fetchall()


@router.post("/{company_id}/employees", response_model=Employee, status_code=201)
def create_employee(company_id: UUID, data: EmployeeInput, connection: Connection):
    try:
        return connection.execute(
            "INSERT INTO employees (id, company_id, display_name) VALUES (%s, %s, %s) RETURNING *",
            (uuid4(), company_id, data.display_name),
        ).fetchone()
    except psycopg.errors.ForeignKeyViolation as error:
        raise HTTPException(404, "Компания не найдена") from error


@router.put("/{company_id}/employees/{employee_id}", response_model=Employee)
def update_employee(
    company_id: UUID, employee_id: UUID, data: EmployeeInput, connection: Connection
):
    employee = connection.execute(
        "UPDATE employees SET display_name = %s WHERE id = %s AND company_id = %s RETURNING *",
        (data.display_name, employee_id, company_id),
    ).fetchone()
    if employee is None:
        raise HTTPException(404, "Сотрудник не найден")
    return employee


@router.delete("/{company_id}/employees/{employee_id}", status_code=204)
def delete_employee(company_id: UUID, employee_id: UUID, connection: Connection):
    try:
        result = connection.execute(
            "DELETE FROM employees WHERE id = %s AND company_id = %s", (employee_id, company_id)
        )
    except psycopg.errors.ForeignKeyViolation as error:
        raise HTTPException(409, "Сотрудник связан со звонками и не может быть удалён") from error
    if result.rowcount == 0:
        raise HTTPException(404, "Сотрудник не найден")
    return Response(status_code=204)
