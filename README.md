# 🚚 Mom And Pop Delivery Database Management System (Renamed as "DeliveryPH")

A complete, production-ready delivery management system using **Oracle XE**, **FastAPI**, and a **mobile-first web UI**. Supports customers, drivers, and admins with full order lifecycle tracking.

---

## 📁 Project Structure

```
delivery-system/
├── backend/
│   ├── main.py            # FastAPI app entry point
│   ├── routers.py         # All API route handlers
│   ├── schemas.py         # Pydantic request/response models
│   ├── database.py        # Oracle connection pool
│   ├── auth.py            # JWT authentication
│   ├── config.py          # Settings / environment variables
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   └── index.html         # Mobile-first SPA (no build step required)
├── database/
│   ├── create_user.sql    # Oracle user creation (run as SYSDBA)
│   ├── schema.sql         # Tables, sequences, triggers, indexes
│   └── procedures.sql     # Stored procedures, views, functions
├── scripts/
│   └── cli.py             # Typer CLI tool
├── tests/
│   └── test_api.py        # Pytest integration tests
├── docker-compose.yml
└── README.md
```

---

## 🏃 Quick Start — Docker (Recommended)

### Prerequisites
- Docker Desktop installed and running
- ~4GB RAM available for Oracle XE

### 1. Start all services

```bash
cd delivery-system
docker-compose up -d
```

Oracle XE takes **2–3 minutes** to fully initialize on first boot. Watch progress:

```bash
docker logs dms_oracle -f
# Wait for: "DATABASE IS READY TO USE!"
docker logs dms_backend -f
# Wait for: "Oracle connection pool ready"
```

### 2. Open the web UI

Navigate to **http://localhost:8000** in your browser.

**Default credentials:**
- Admin: `admin@delivery.com` / `admin123`

### 3. Verify health

```bash
curl http://localhost:8000/health
```

---

## 🖥️ Local Development (Without Docker)

### Prerequisites
- Python 3.11+
- Oracle XE 21c installed locally OR Oracle Instant Client
- Oracle XE running on `localhost:1521`

### 1. Set up Oracle database

```bash
# Connect as SYSDBA
sqlplus sys/your_password@localhost:1521/XEPDB1 as sysdba

# Run user creation script
@database/create_user.sql

# Connect as delivery_user
sqlplus delivery_user/OraclePass123@localhost:1521/XEPDB1

# Run schema and procedures
@database/schema.sql
@database/procedures.sql
exit
```

### 2. Set up Python environment

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your Oracle connection details
```

### 4. Start the backend

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Open the UI

Visit **http://localhost:8000**

---

## 🗄️ Oracle Database Design

### Tables

| Table | Description |
|-------|-------------|
| `USERS` | All users (customers, drivers, admins) |
| `DRIVERS` | Driver profiles linked to users |
| `ORDERS` | Customer delivery orders |
| `DELIVERIES` | Delivery assignments and status tracking |
| `AUDIT_LOGS` | Auto-generated audit trail |

### Sequences
- `USERS_SEQ` — User ID generation (starts at 1)
- `ORDERS_SEQ` — Order ID generation (starts at 1000)
- `DRIVERS_SEQ` — Driver ID generation
- `DELIVERIES_SEQ` — Delivery ID generation
- `AUDIT_SEQ` — Audit log ID generation

### Triggers
- `TRG_USERS_BI/BU` — Auto-ID + updated_at timestamp
- `TRG_ORDERS_BI/BU` — Auto-ID + timestamps
- `TRG_DRIVERS_BI` — Auto-ID for drivers
- `TRG_DELIVERIES_BI` — Auto-ID for deliveries
- `TRG_ORDERS_AUDIT` — Auto-logs every status change to AUDIT_LOGS

### Stored Procedures
- `CREATE_ORDER(...)` — Validates customer, creates order
- `ASSIGN_DRIVER(...)` — Validates availability, creates delivery, updates statuses
- `UPDATE_DELIVERY_STATUS(...)` — Validates transitions, updates timestamps, frees driver
- `CANCEL_ORDER(...)` — Cancels order and frees driver if assigned

### Functions
- `GET_AVAILABLE_DRIVER()` — Returns best available driver (round-robin by delivery count)

### Views
- `V_ORDER_SUMMARY` — Joined order/delivery/driver/customer view
- `V_DRIVER_STATS` — Driver performance metrics with avg delivery time

---

## 🔄 Order Status Lifecycle

```
Customer places order → PENDING
Admin assigns driver  → ASSIGNED
Driver picks up       → PICKED_UP
Driver in route       → IN_TRANSIT
Driver delivers       → DELIVERED

Any cancellable state → CANCELLED
```

---

## 🌐 API Endpoints

### Authentication
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login, get JWT token |
| GET  | `/api/auth/me` | Get current user info |

### Orders
| Method | Path | Description | Role |
|--------|------|-------------|------|
| POST | `/api/orders` | Place new order | Customer |
| GET  | `/api/orders` | List orders (filtered by role) | All |
| GET  | `/api/orders/{id}` | Get specific order | All |
| DELETE | `/api/orders/{id}` | Cancel order | Customer/Admin |

### Drivers
| Method | Path | Description | Role |
|--------|------|-------------|------|
| GET  | `/api/drivers` | List all drivers | All |
| PATCH | `/api/drivers/{id}/status` | Update availability | Driver/Admin |

### Deliveries
| Method | Path | Description | Role |
|--------|------|-------------|------|
| POST | `/api/deliveries/assign` | Assign driver to order | Admin |
| PATCH | `/api/deliveries/{id}/status` | Update delivery status | Driver |
| GET  | `/api/deliveries/my` | Get my deliveries | Driver |

### Admin
| Method | Path | Description | Role |
|--------|------|-------------|------|
| GET  | `/api/admin/analytics` | System analytics | Admin |
| GET  | `/api/admin/users` | List all users | Admin |
| PATCH | `/api/admin/users/{id}/toggle` | Activate/deactivate user | Admin |
| GET  | `/api/admin/auto-assign/{order_id}` | Auto-assign best driver | Admin |

Full interactive docs at: **http://localhost:8000/docs**

---

## 🖥️ CLI Usage

```bash
cd scripts
pip install -r ../backend/requirements.txt
```

### Commands

```bash
# Register a new user (interactive prompts)
python cli.py create-user

# Login
python cli.py login

# Place an order
python cli.py place-order

# List your orders
python cli.py list-orders

# Track a specific order
python cli.py track-order 1001

# List all drivers (any user)
python cli.py list-drivers

# Assign driver to order (admin)
python cli.py assign-driver 1001 2

# Auto-assign best available driver (admin)
python cli.py auto-assign 1001

# Driver: update delivery status
python cli.py update-status 1 picked_up
python cli.py update-status 1 in_transit
python cli.py update-status 1 delivered --notes "Left at front door"

# Driver: view my deliveries
python cli.py my-deliveries

# Admin: view analytics
python cli.py analytics

# Run complete simulation (creates test users and flows through full lifecycle)
python cli.py simulate-full-flow
```

---

## 🧪 Running Tests

```bash
# Start backend first (Docker or local)
cd tests
pip install pytest httpx
pytest test_api.py -v
```

---

## 🐳 Docker Management

```bash
# Start
docker-compose up -d

# Stop (keeps data)
docker-compose stop

# Stop and remove containers (keeps volume data)
docker-compose down

# Wipe everything including DB data
docker-compose down -v

# Rebuild backend after code changes
docker-compose up -d --build backend

# View logs
docker logs dms_oracle -f
docker logs dms_backend -f

# Connect to Oracle directly
docker exec -it dms_oracle sqlplus delivery_user/OraclePass123@XEPDB1
```

---

## 🔒 Security Notes

- **JWT tokens** expire after 24 hours
- **Passwords** are hashed with bcrypt (cost factor 12)
- **Role-based access control** enforced on all endpoints
- Change `SECRET_KEY` in `.env` before any real deployment
- Oracle password in `docker-compose.yml` should be changed for production

---

## 🐛 Troubleshooting

**Oracle won't start:**
- Ensure Docker has at least 4GB RAM allocated
- Check: `docker logs dms_oracle`
- Oracle XE takes 2–3 min on first boot

**Backend can't connect to Oracle:**
- Verify Oracle is healthy: `docker ps` — look for `(healthy)`
- Check DSN format: `hostname:port/service_name`
- For thin mode (default), no Instant Client needed

**`ORA-01017: invalid username/password`:**
- Re-run `create_user.sql` as SYSDBA
- Verify `ORACLE_USER` and `ORACLE_PASSWORD` in `.env`

**Port 1521 already in use:**
- Change host port in `docker-compose.yml`: `"1522:1521"`
- Update `ORACLE_DSN=localhost:1522/XEPDB1`
