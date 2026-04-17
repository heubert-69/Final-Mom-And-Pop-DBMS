from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
import logging

from config import get_settings
from database import create_pool, close_pool, get_connection
from routers import auth_router, orders_router, drivers_router, deliveries_router, admin_router
from auth import hash_password

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _init_admin():
    """Ensure admin exists and has a valid bcrypt hash."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, password_hash FROM users WHERE email = 'admin@delivery.com'"
        )
        row = cursor.fetchone()

        if row:
            # Fix placeholder hash
            if row[1] and "placeholder" in row[1]:
                cursor.execute(
                    "UPDATE users SET password_hash = :1 WHERE email = 'admin@delivery.com'",
                    [hash_password("admin123")],
                )
                conn.commit()
                logger.info("Admin password fixed — login: admin@delivery.com / admin123")
        else:
            # Create admin if missing
            cursor.execute(
                """
                INSERT INTO users (name, email, password_hash, role)
                VALUES (:1, :2, :3, 'admin')
                """,
                ("System Admin", "admin@delivery.com", hash_password("admin123")),
            )
            conn.commit()
            logger.info("Admin created — login: admin@delivery.com / admin123")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.warning(f"_init_admin failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to Oracle …")
    create_pool()   # sync
    _init_admin()   # sync call (no await)
    logger.info("Oracle connection pool ready ✓")
    yield
    close_pool()    # sync
    logger.info("Oracle pool closed")


app = FastAPI(
    title="DeliverPH — Delivery Management System",
    version="1.0.0",
    description="Oracle-backed order & delivery management API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router,       prefix="/api")
app.include_router(orders_router,     prefix="/api")
app.include_router(drivers_router,    prefix="/api")
app.include_router(deliveries_router, prefix="/api")
app.include_router(admin_router,      prefix="/api")

_frontend = os.environ.get("FRONTEND_PATH", "/app/frontend")
logger.info(f"Frontend path: {_frontend} — exists: {os.path.isdir(_frontend)}")

if os.path.isdir(_frontend):
    app.mount("/static", StaticFiles(directory=_frontend), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_ui():
        return FileResponse(os.path.join(_frontend, "index.html"))


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "DeliverPH"}