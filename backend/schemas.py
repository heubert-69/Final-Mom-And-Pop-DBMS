from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Literal
from datetime import datetime


# ── Auth ───────────────────────────────────────────────────
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: Literal["customer", "driver", "admin"] = "customer"
    vehicle_type: Optional[str] = "motorcycle"
    license_plate: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str
    name: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


# ── Orders ─────────────────────────────────────────────────
class OrderCreate(BaseModel):
    pickup_address: str
    dropoff_address: str
    package_desc: Optional[str] = None
    total_amount: Optional[float] = 0.0
    notes: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    customer_id: int
    customer_name: Optional[str] = None
    pickup_address: str
    dropoff_address: str
    package_desc: Optional[str] = None
    status: str
    total_amount: float
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    driver_name: Optional[str] = None
    delivery_status: Optional[str] = None
    delivery_id: Optional[int] = None


# ── Drivers ────────────────────────────────────────────────
class DriverOut(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    vehicle_type: str
    license_plate: Optional[str] = None
    availability_status: str
    total_deliveries: int
    rating: float


# ── Deliveries ─────────────────────────────────────────────
class AssignDriver(BaseModel):
    order_id: int
    driver_id: int


class DeliveryStatusUpdate(BaseModel):
    new_status: Literal["picked_up", "in_transit", "delivered", "failed"]
    driver_notes: Optional[str] = None


class DeliveryOut(BaseModel):
    id: int
    order_id: int
    driver_id: Optional[int] = None
    driver_name: Optional[str] = None
    status: str
    assigned_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    driver_notes: Optional[str] = None
    estimated_minutes: Optional[int] = None
    delivery_minutes: Optional[float] = None


# ── Analytics ──────────────────────────────────────────────
class AnalyticsSummary(BaseModel):
    total_orders: int
    pending_orders: int
    assigned_orders: int
    in_transit_orders: int
    delivered_orders: int
    cancelled_orders: int
    total_drivers: int
    available_drivers: int
    busy_drivers: int
    total_customers: int
    avg_delivery_minutes: Optional[float] = None
