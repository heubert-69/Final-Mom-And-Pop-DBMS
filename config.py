from fastapi import APIRouter, Depends, HTTPException
import oracledb
from database import get_db
from schemas import (
    UserRegister, UserLogin, Token, UserOut,
    OrderCreate, OrderOut,
    AssignDriver, DeliveryStatusUpdate, DeliveryOut,
    DriverOut, AnalyticsSummary,
)
from auth import hash_password, verify_password, create_access_token, get_current_user, require_role

# ─────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


@auth_router.post("/register", response_model=UserOut, status_code=201)
async def register(data: UserRegister, db=Depends(get_db)):
    cursor = db.cursor()
    try:
        await cursor.execute("SELECT id FROM users WHERE email = :1", [data.email])
        if await cursor.fetchone():
            raise HTTPException(400, "Email already registered")

        pw_hash = hash_password(data.password)
        user_id_var = cursor.var(oracledb.NUMBER)

        await cursor.execute(
            "INSERT INTO users (name, email, password_hash, role) "
            "VALUES (:1, :2, :3, :4) RETURNING id INTO :5",
            [data.name, data.email, pw_hash, data.role, user_id_var],
        )
        user_id = int(user_id_var.getvalue()[0])

        if data.role == "driver":
            await cursor.execute(
                "INSERT INTO drivers (user_id, vehicle_type, license_plate) VALUES (:1, :2, :3)",
                [user_id, data.vehicle_type or "motorcycle", data.license_plate],
            )

        await db.commit()

        await cursor.execute(
            "SELECT id, name, email, role, is_active, created_at FROM users WHERE id = :1",
            [user_id],
        )
        row = await cursor.fetchone()
        return UserOut(id=row[0], name=row[1], email=row[2],
                       role=row[3], is_active=bool(row[4]), created_at=row[5])
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, str(e))
    finally:
        cursor.close()


@auth_router.post("/login", response_model=Token)
async def login(data: UserLogin, db=Depends(get_db)):
    cursor = db.cursor()
    try:
        await cursor.execute(
            "SELECT id, name, password_hash, role, is_active FROM users WHERE email = :1",
            [data.email],
        )
        row = await cursor.fetchone()
        if not row or not verify_password(data.password, row[2]):
            raise HTTPException(401, "Invalid email or password")
        if not row[4]:
            raise HTTPException(403, "Account is inactive")

        token = create_access_token({"sub": str(row[0]), "role": row[3], "name": row[1]})
        return Token(access_token=token, user_id=row[0], role=row[3], name=row[1])
    finally:
        cursor.close()


@auth_router.get("/me", response_model=UserOut)
async def me(current_user=Depends(get_current_user), db=Depends(get_db)):
    cursor = db.cursor()
    try:
        await cursor.execute(
            "SELECT id, name, email, role, is_active, created_at FROM users WHERE id = :1",
            [int(current_user["user_id"])],
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        return UserOut(id=row[0], name=row[1], email=row[2],
                       role=row[3], is_active=bool(row[4]), created_at=row[5])
    finally:
        cursor.close()


# ─────────────────────────────────────────────────────────────
# ORDERS
# ─────────────────────────────────────────────────────────────
orders_router = APIRouter(prefix="/orders", tags=["Orders"])

# Base query used across all order endpoints
_ORDER_Q = """
    SELECT o.id, o.customer_id, u.name, o.pickup_address, o.dropoff_address,
           o.package_desc, o.status, o.total_amount, o.notes,
           o.created_at, o.updated_at,
           du.name, d.status, d.id
    FROM orders o
    JOIN users u ON u.id = o.customer_id
    LEFT JOIN deliveries d ON d.order_id = o.id
    LEFT JOIN drivers dr ON kr.id = d.driver_id
    LEFT JOIN users du ON du.id = kr.user_id
"""

# Correct version without the typo above
_ORDER_QUERY = """
    SELECT o.id, o.customer_id, u.name, o.pickup_address, o.dropoff_address,
           o.package_desc, o.status, o.total_amount, o.notes,
           o.created_at, o.updated_at,
           du.name AS driver_name, d.status AS delivery_status, d.id AS delivery_id
    FROM orders o
    JOIN users u ON u.id = o.customer_id
    LEFT JOIN deliveries d ON d.order_id = o.id
    LEFT JOIN drivers dr ON dr.id = d.driver_id
    LEFT JOIN users du ON du.id = dr.user_id
"""


def _row_to_order(row) -> OrderOut:
    return OrderOut(
        id=row[0], customer_id=row[1], customer_name=row[2],
        pickup_address=row[3], dropoff_address=row[4], package_desc=row[5],
        status=row[6], total_amount=float(row[7] or 0), notes=row[8],
        created_at=row[9], updated_at=row[10],
        driver_name=row[11], delivery_status=row[12], delivery_id=row[13],
    )


@orders_router.post("", response_model=OrderOut, status_code=201)
async def create_order(data: OrderCreate, current_user=Depends(get_current_user), db=Depends(get_db)):
    if current_user["role"] not in ("customer", "admin"):
        raise HTTPException(403, "Only customers can place orders")

    cursor = db.cursor()
    try:
        order_id_var = cursor.var(oracledb.NUMBER)
        status_var = cursor.var(oracledb.STRING)

        await cursor.callproc("create_order", [
            int(current_user["user_id"]),
            data.pickup_address,
            data.dropoff_address,
            data.package_desc,
            data.total_amount,
            data.notes,
            order_id_var,
            status_var,
        ])

        msg = status_var.getvalue()
        if not msg or not msg.startswith("SUCCESS"):
            raise HTTPException(400, msg or "Order creation failed")

        order_id = int(order_id_var.getvalue())
        await cursor.execute(_ORDER_QUERY + " WHERE o.id = :1", [order_id])
        row = await cursor.fetchone()
        return _row_to_order(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cursor.close()


@orders_router.get("", response_model=list[OrderOut])
async def list_orders(current_user=Depends(get_current_user), db=Depends(get_db)):
    cursor = db.cursor()
    try:
        role = current_user["role"]
        uid = int(current_user["user_id"])

        if role == "customer":
            await cursor.execute(
                _ORDER_QUERY + " WHERE o.customer_id = :1 ORDER BY o.created_at DESC", [uid]
            )
        elif role == "driver":
            await cursor.execute(
                _ORDER_QUERY + """
                WHERE d.driver_id = (SELECT id FROM drivers WHERE user_id = :1)
                ORDER BY o.created_at DESC""",
                [uid],
            )
        else:  # admin
            await cursor.execute(_ORDER_QUERY + " ORDER BY o.created_at DESC")

        rows = await cursor.fetchall()
        return [_row_to_order(r) for r in rows]
    finally:
        cursor.close()


@orders_router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, current_user=Depends(get_current_user), db=Depends(get_db)):
    cursor = db.cursor()
    try:
        await cursor.execute(_ORDER_QUERY + " WHERE o.id = :1", [order_id])
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Order not found")

        uid = int(current_user["user_id"])
        role = current_user["role"]
        if role == "customer" and row[1] != uid:
            raise HTTPException(403, "Not your order")

        return _row_to_order(row)
    finally:
        cursor.close()


@orders_router.delete("/{order_id}")
async def cancel_order(order_id: int, current_user=Depends(get_current_user), db=Depends(get_db)):
    cursor = db.cursor()
    try:
        status_var = cursor.var(oracledb.STRING)
        await cursor.callproc("cancel_order", [order_id, int(current_user["user_id"]), status_var])
        msg = status_var.getvalue()
        if not msg or not msg.startswith("SUCCESS"):
            raise HTTPException(400, msg or "Cancel failed")
        # procedure commits internally — no extra commit needed
        return {"message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cursor.close()


# ─────────────────────────────────────────────────────────────
# DRIVERS
# ─────────────────────────────────────────────────────────────
drivers_router = APIRouter(prefix="/drivers", tags=["Drivers"])


@drivers_router.get("", response_model=list[DriverOut])
async def list_drivers(current_user=Depends(get_current_user), db=Depends(get_db)):
    cursor = db.cursor()
    try:
        await cursor.execute("""
            SELECT dr.id, dr.user_id, u.name, u.email,
                   dr.vehicle_type, dr.license_plate,
                   dr.availability_status, dr.total_deliveries, dr.rating
            FROM drivers dr
            JOIN users u ON u.id = dr.user_id
            ORDER BY dr.availability_status, dr.total_deliveries
        """)
        rows = await cursor.fetchall()
        return [DriverOut(
            id=r[0], user_id=r[1], name=r[2], email=r[3],
            vehicle_type=r[4] or "motorcycle", license_plate=r[5],
            availability_status=r[6], total_deliveries=int(r[7] or 0),
            rating=float(r[8] or 5.0),
        ) for r in rows]
    finally:
        cursor.close()


@drivers_router.patch("/{driver_id}/status")
async def update_driver_status(
    driver_id: int, availability: str,
    current_user=Depends(get_current_user), db=Depends(get_db),
):
    if availability not in ("available", "busy", "offline"):
        raise HTTPException(400, "Invalid status. Use: available, busy, offline")

    cursor = db.cursor()
    try:
        role = current_user["role"]
        uid = int(current_user["user_id"])

        if role == "driver":
            await cursor.execute(
                "SELECT id FROM drivers WHERE id = :1 AND user_id = :2", [driver_id, uid]
            )
            if not await cursor.fetchone():
                raise HTTPException(403, "Not your driver profile")
        elif role != "admin":
            raise HTTPException(403, "Not authorised")

        await cursor.execute(
            "UPDATE drivers SET availability_status = :1 WHERE id = :2",
            [availability, driver_id],
        )
        await db.commit()
        return {"message": f"Driver status updated to {availability}"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, str(e))
    finally:
        cursor.close()


# ─────────────────────────────────────────────────────────────
# DELIVERIES
# ─────────────────────────────────────────────────────────────
deliveries_router = APIRouter(prefix="/deliveries", tags=["Deliveries"])


@deliveries_router.post("/assign")
async def assign_driver_to_order(
    data: AssignDriver,
    current_user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    cursor = db.cursor()
    try:
        delivery_id_var = cursor.var(oracledb.NUMBER)
        status_var = cursor.var(oracledb.STRING)
        await cursor.callproc("assign_driver", [
            data.order_id, data.driver_id,
            int(current_user["user_id"]),
            delivery_id_var, status_var,
        ])
        msg = status_var.getvalue()
        if not msg or not msg.startswith("SUCCESS"):
            raise HTTPException(400, msg or "Assignment failed")
        # procedure commits internally
        return {"message": msg, "delivery_id": int(delivery_id_var.getvalue())}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cursor.close()


@deliveries_router.patch("/{delivery_id}/status")
async def update_delivery_status(
    delivery_id: int,
    data: DeliveryStatusUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    if current_user["role"] not in ("driver", "admin"):
        raise HTTPException(403, "Only drivers can update delivery status")

    cursor = db.cursor()
    try:
        status_var = cursor.var(oracledb.STRING)
        await cursor.callproc("update_delivery_status", [
            delivery_id,
            int(current_user["user_id"]),
            data.new_status,
            data.driver_notes,
            status_var,
        ])
        msg = status_var.getvalue()
        if not msg or not msg.startswith("SUCCESS"):
            raise HTTPException(400, msg or "Status update failed")
        # procedure commits internally
        return {"message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cursor.close()


@deliveries_router.get("/my", response_model=list[DeliveryOut])
async def my_deliveries(current_user=Depends(get_current_user), db=Depends(get_db)):
    if current_user["role"] not in ("driver", "admin"):
        raise HTTPException(403, "Only drivers can view their deliveries")

    cursor = db.cursor()
    try:
        uid = int(current_user["user_id"])
        await cursor.execute("""
            SELECT d.id, d.order_id, d.driver_id, u.name,
                   d.status, d.assigned_at, d.picked_up_at, d.delivered_at,
                   d.driver_notes, d.estimated_minutes,
                   CASE
                     WHEN d.delivered_at IS NOT NULL AND d.assigned_at IS NOT NULL
                     THEN ROUND(
                       (CAST(d.delivered_at AS DATE) - CAST(d.assigned_at AS DATE)) * 24 * 60, 1)
                   END AS delivery_minutes
            FROM deliveries d
            JOIN drivers dr ON dr.id = d.driver_id
            JOIN users u ON u.id = dr.user_id
            WHERE dr.user_id = :1
            ORDER BY d.assigned_at DESC
        """, [uid])
        rows = await cursor.fetchall()
        return [DeliveryOut(
            id=r[0], order_id=r[1], driver_id=r[2], driver_name=r[3],
            status=r[4], assigned_at=r[5], picked_up_at=r[6], delivered_at=r[7],
            driver_notes=r[8], estimated_minutes=r[9], delivery_minutes=r[10],
        ) for r in rows]
    finally:
        cursor.close()


# ─────────────────────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────────────────────
admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@admin_router.get("/analytics", response_model=AnalyticsSummary)
async def get_analytics(current_user=Depends(require_role("admin")), db=Depends(get_db)):
    cursor = db.cursor()
    try:
        await cursor.execute("""
            SELECT
              COUNT(*),
              SUM(CASE WHEN status = 'pending'                   THEN 1 ELSE 0 END),
              SUM(CASE WHEN status = 'assigned'                  THEN 1 ELSE 0 END),
              SUM(CASE WHEN status IN ('picked_up','in_transit') THEN 1 ELSE 0 END),
              SUM(CASE WHEN status = 'delivered'                 THEN 1 ELSE 0 END),
              SUM(CASE WHEN status = 'cancelled'                 THEN 1 ELSE 0 END)
            FROM orders
        """)
        o = await cursor.fetchone()

        await cursor.execute("""
            SELECT COUNT(*),
              SUM(CASE WHEN availability_status = 'available' THEN 1 ELSE 0 END),
              SUM(CASE WHEN availability_status = 'busy'      THEN 1 ELSE 0 END)
            FROM drivers
        """)
        d = await cursor.fetchone()

        await cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'")
        cust = (await cursor.fetchone())[0]

        await cursor.execute("""
            SELECT AVG(
              ROUND((CAST(delivered_at AS DATE) - CAST(assigned_at AS DATE)) * 24 * 60, 1))
            FROM deliveries
            WHERE delivered_at IS NOT NULL
        """)
        avg_row = await cursor.fetchone()

        return AnalyticsSummary(
            total_orders=int(o[0] or 0),
            pending_orders=int(o[1] or 0),
            assigned_orders=int(o[2] or 0),
            in_transit_orders=int(o[3] or 0),
            delivered_orders=int(o[4] or 0),
            cancelled_orders=int(o[5] or 0),
            total_drivers=int(d[0] or 0),
            available_drivers=int(d[1] or 0),
            busy_drivers=int(d[2] or 0),
            total_customers=int(cust or 0),
            avg_delivery_minutes=float(avg_row[0]) if avg_row and avg_row[0] else None,
        )
    finally:
        cursor.close()


@admin_router.get("/users", response_model=list[UserOut])
async def list_users(current_user=Depends(require_role("admin")), db=Depends(get_db)):
    cursor = db.cursor()
    try:
        await cursor.execute(
            "SELECT id, name, email, role, is_active, created_at FROM users ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [UserOut(id=r[0], name=r[1], email=r[2],
                        role=r[3], is_active=bool(r[4]), created_at=r[5])
                for r in rows]
    finally:
        cursor.close()


@admin_router.patch("/users/{user_id}/toggle")
async def toggle_user(
    user_id: int,
    current_user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    cursor = db.cursor()
    try:
        await cursor.execute(
            "UPDATE users SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = :1",
            [user_id],
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "User not found")
        await db.commit()
        return {"message": "User status toggled"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, str(e))
    finally:
        cursor.close()


@admin_router.get("/auto-assign/{order_id}")
async def auto_assign(
    order_id: int,
    current_user=Depends(require_role("admin")),
    db=Depends(get_db),
):
    cursor = db.cursor()
    try:
        await cursor.execute("SELECT get_available_driver() FROM dual")
        row = await cursor.fetchone()
        driver_id = row[0] if row else None
        if not driver_id:
            raise HTTPException(404, "No available drivers at this time")

        delivery_id_var = cursor.var(oracledb.NUMBER)
        status_var = cursor.var(oracledb.STRING)
        await cursor.callproc("assign_driver", [
            order_id, int(driver_id), int(current_user["user_id"]),
            delivery_id_var, status_var,
        ])
        msg = status_var.getvalue()
        if not msg or not msg.startswith("SUCCESS"):
            raise HTTPException(400, msg or "Auto-assign failed")
        # procedure commits internally
        return {
            "message": msg,
            "driver_id": int(driver_id),
            "delivery_id": int(delivery_id_var.getvalue()),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cursor.close()
