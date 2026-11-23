"""
Companies (v1.2, many companies on one system). Platform admin only
(see tenancy.PLATFORM_ONLY and auth.ADMIN_ONLY).

GET    /api/companies                            list companies with their devices and users
POST   /api/companies                            create a company (+ optionally its first admin)
PUT    /api/companies/{id}                       rename / change the sector
DELETE /api/companies/{id}                       delete a company (its users and devices must be moved first)
PUT    /api/companies/devices/{device_id}        give a device to a company ({"company_id": null} = platform)
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, tenancy
from app.database import get_db
from app.models import Company, CompanyDevice, CompanyMember, Device, User
from app.websocket_manager import manager

router = APIRouter(prefix="/api/companies", tags=["companies"])


class CompanyIn(BaseModel):
    company_id: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=2, max_length=100)
    sector: str = Field(default="", max_length=40)
    admin_username: str | None = Field(default=None, min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    admin_password: str | None = Field(default=None, max_length=200)


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    sector: str | None = Field(default=None, max_length=40)


class Assign(BaseModel):
    company_id: str | None = None


def company_dict(db: Session, c: Company) -> dict:
    devices = sorted(r.device_id for r in db.query(CompanyDevice).filter(CompanyDevice.company_id == c.company_id))
    users = sorted(m.username for m in db.query(CompanyMember).filter(CompanyMember.company_id == c.company_id))
    return {**c.to_dict(), "devices": devices, "users": users}


@router.get("")
def list_companies(db: Session = Depends(get_db)):
    owned = {r.device_id for r in db.query(CompanyDevice)}
    platform_devices = sorted(d for (d,) in db.query(Device.device_id) if d not in owned)
    return {"companies": [company_dict(db, c) for c in db.query(Company).order_by(Company.name)],
            "platform_devices": platform_devices}


@router.post("", status_code=201)
def create_company(body: CompanyIn, db: Session = Depends(get_db)):
    if db.get(Company, body.company_id) is not None:
        raise HTTPException(status_code=409, detail=f"Company '{body.company_id}' already exists.")
    if body.admin_username:
        if db.get(User, body.admin_username) is not None:
            raise HTTPException(status_code=409, detail=f"User '{body.admin_username}' already exists.")
        problem = auth.password_problem(body.admin_password or "")
        if problem:
            raise HTTPException(status_code=400, detail=problem)
    company = Company(company_id=body.company_id, name=body.name.strip(), sector=body.sector.strip())
    db.add(company)
    if body.admin_username:
        db.add(User(username=body.admin_username, password_hash=auth.hash_password(body.admin_password), role="admin"))
        db.add(CompanyMember(username=body.admin_username, company_id=body.company_id))
    db.commit()
    return {"created": True, "company": company_dict(db, company)}


@router.put("/{company_id}")
def update_company(company_id: str, body: CompanyUpdate, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found.")
    if body.name is not None:
        company.name = body.name.strip()
    if body.sector is not None:
        company.sector = body.sector.strip()
    db.commit()
    return {"updated": True, "company": company_dict(db, company)}


@router.delete("/{company_id}")
def delete_company(company_id: str, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found.")
    info = company_dict(db, company)
    if info["users"] or info["devices"]:
        raise HTTPException(status_code=409, detail="Move or delete this company's users and devices first "
                            f"(users: {', '.join(info['users']) or '-'}; devices: {', '.join(info['devices']) or '-'}).")
    db.delete(company)
    db.commit()
    return {"deleted": True, "company_id": company_id}


@router.put("/devices/{device_id}")
async def assign_device(device_id: str, body: Assign, db: Session = Depends(get_db)):
    device_id = device_id.upper()
    if db.get(Device, device_id) is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")
    if body.company_id and db.get(Company, body.company_id) is None:
        raise HTTPException(status_code=404, detail=f"Company '{body.company_id}' not found.")
    db.query(CompanyDevice).filter(CompanyDevice.device_id == device_id).delete()
    if body.company_id:
        db.add(CompanyDevice(device_id=device_id, company_id=body.company_id))
    db.commit()
    tenancy.refresh(db)
    # browsers reload their device list (a company may have gained or lost a device)
    await manager.broadcast("companies_changed", {"device_id": device_id, "company_id": body.company_id})
    return {"device_id": device_id, "company_id": body.company_id}
