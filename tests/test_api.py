"""
Integration tests for the Delivery Management System API.
Requires the backend to be running at http://localhost:8000
Run with: pytest tests/ -v
"""
import pytest
import httpx
import random

BASE = "http://localhost:8000/api"
suffix = random.randint(10000, 99999)


class TestAuth:
    def test_register_customer(self):
        r = httpx.post(f"{BASE}/auth/register", json={
            "name": f"Test Customer {suffix}",
            "email": f"customer{suffix}@test.com",
            "password": "testpass123",
            "role": "customer",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["role"] == "customer"
        assert data["email"] == f"customer{suffix}@test.com"

    def test_register_driver(self):
        r = httpx.post(f"{BASE}/auth/register", json={
            "name": f"Test Driver {suffix}",
            "email": f"driver{suffix}@test.com",
            "password": "testpass123",
            "role": "driver",
            "vehicle_type": "motorcycle",
        })
        assert r.status_code == 201
        assert r.json()["role"] == "driver"

    def test_duplicate_email(self):
        r = httpx.post(f"{BASE}/auth/register", json={
            "name": "Dup", "email": f"customer{suffix}@test.com",
            "password": "testpass123", "role": "customer",
        })
        assert r.status_code == 400

    def test_login_success(self):
        r = httpx.post(f"{BASE}/auth/login", json={
            "email": f"customer{suffix}@test.com",
            "password": "testpass123",
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["role"] == "customer"

    def test_login_bad_password(self):
        r = httpx.post(f"{BASE}/auth/login", json={
            "email": f"customer{suffix}@test.com",
            "password": "wrongpass",
        })
        assert r.status_code == 401

    def test_admin_login(self):
        r = httpx.post(f"{BASE}/auth/login", json={
            "email": "admin@delivery.com",
            "password": "admin123",
        })
        assert r.status_code == 200
        assert r.json()["role"] == "admin"


class TestFullFlow:
    """Test complete order lifecycle."""

    @pytest.fixture(scope="class")
    def tokens(self):
        tokens = {}
        for role in ["customer", "driver", "admin"]:
            email = f"customer{suffix}@test.com" if role == "customer" \
                else f"driver{suffix}@test.com" if role == "driver" \
                else "admin@delivery.com"
            pw = "testpass123" if role != "admin" else "admin123"
            r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
            tokens[role] = r.json()["access_token"]
        return tokens

    def auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_place_order(self, tokens):
        r = httpx.post(f"{BASE}/orders", json={
            "pickup_address": "123 Test St",
            "dropoff_address": "456 Test Ave",
            "package_desc": "Test package",
            "total_amount": 150.0,
        }, headers=self.auth(tokens["customer"]))
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "pending"
        TestFullFlow.order_id = data["id"]

    def test_list_orders(self, tokens):
        r = httpx.get(f"{BASE}/orders", headers=self.auth(tokens["customer"]))
        assert r.status_code == 200
        assert any(o["id"] == TestFullFlow.order_id for o in r.json())

    def test_customer_cannot_assign(self, tokens):
        r = httpx.post(f"{BASE}/deliveries/assign", json={
            "order_id": TestFullFlow.order_id, "driver_id": 1
        }, headers=self.auth(tokens["customer"]))
        assert r.status_code == 403

    def test_auto_assign(self, tokens):
        r = httpx.get(
            f"{BASE}/admin/auto-assign/{TestFullFlow.order_id}",
            headers=self.auth(tokens["admin"])
        )
        assert r.status_code == 200
        TestFullFlow.delivery_id = r.json()["delivery_id"]

    def test_order_now_assigned(self, tokens):
        r = httpx.get(f"{BASE}/orders/{TestFullFlow.order_id}",
                      headers=self.auth(tokens["admin"]))
        assert r.json()["status"] == "assigned"

    def test_driver_update_picked_up(self, tokens):
        r = httpx.patch(
            f"{BASE}/deliveries/{TestFullFlow.delivery_id}/status",
            json={"new_status": "picked_up", "driver_notes": "Picked up from sender"},
            headers=self.auth(tokens["driver"])
        )
        assert r.status_code == 200

    def test_driver_update_in_transit(self, tokens):
        r = httpx.patch(
            f"{BASE}/deliveries/{TestFullFlow.delivery_id}/status",
            json={"new_status": "in_transit"},
            headers=self.auth(tokens["driver"])
        )
        assert r.status_code == 200

    def test_driver_update_delivered(self, tokens):
        r = httpx.patch(
            f"{BASE}/deliveries/{TestFullFlow.delivery_id}/status",
            json={"new_status": "delivered", "driver_notes": "Left at door"},
            headers=self.auth(tokens["driver"])
        )
        assert r.status_code == 200

    def test_order_delivered(self, tokens):
        r = httpx.get(f"{BASE}/orders/{TestFullFlow.order_id}",
                      headers=self.auth(tokens["customer"]))
        assert r.json()["status"] == "delivered"

    def test_analytics(self, tokens):
        r = httpx.get(f"{BASE}/admin/analytics", headers=self.auth(tokens["admin"]))
        assert r.status_code == 200
        data = r.json()
        assert "total_orders" in data
        assert data["delivered_orders"] > 0


class TestHealthCheck:
    def test_health(self):
        r = httpx.get("http://localhost:8000/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
