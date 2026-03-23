#!/usr/bin/env python3
"""
Delivery Management System - CLI Tool
Usage: python cli.py [command] [options]
"""
import typer
import httpx
import json
import os
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

app = typer.Typer(name="dms", help="Delivery Management System CLI", add_completion=False)
console = Console()

API_BASE = os.getenv("API_BASE", "http://localhost:8000/api")
TOKEN_FILE = os.path.expanduser("~/.dms_token")


def _save_token(token: str, role: str, name: str, user_id: int):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"token": token, "role": role, "name": name, "user_id": user_id}, f)


def _load_token() -> dict:
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        console.print("[red]Not logged in. Run: python cli.py login[/red]")
        raise typer.Exit(1)


def _headers() -> dict:
    data = _load_token()
    return {"Authorization": f"Bearer {data['token']}"}


def _get(path: str, **kwargs) -> dict:
    r = httpx.get(f"{API_BASE}{path}", headers=_headers(), **kwargs)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict, auth: bool = True, **kwargs) -> dict:
    h = _headers() if auth else {}
    r = httpx.post(f"{API_BASE}{path}", json=body, headers=h, **kwargs)
    r.raise_for_status()
    return r.json()


def _patch(path: str, body: dict = None, **kwargs) -> dict:
    r = httpx.patch(f"{API_BASE}{path}", json=body or {}, headers=_headers(), **kwargs)
    r.raise_for_status()
    return r.json()


def _delete(path: str, **kwargs) -> dict:
    r = httpx.delete(f"{API_BASE}{path}", headers=_headers(), **kwargs)
    r.raise_for_status()
    return r.json()


# ─── COMMANDS ──────────────────────────────────────────────────

@app.command("create-user")
def create_user(
    name: str = typer.Option(..., prompt="Full name"),
    email: str = typer.Option(..., prompt="Email"),
    password: str = typer.Option(..., prompt="Password", hide_input=True),
    role: str = typer.Option("customer", prompt="Role (customer/driver/admin)"),
    vehicle: str = typer.Option("motorcycle", prompt="Vehicle type (drivers only)"),
):
    """Register a new user."""
    try:
        data = _post("/auth/register", {
            "name": name, "email": email, "password": password,
            "role": role, "vehicle_type": vehicle,
        }, auth=False)
        console.print(Panel(
            f"[green]✓ User created![/green]\n"
            f"ID: {data['id']}\nName: {data['name']}\nRole: {data['role']}",
            title="Registration Successful"
        ))
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("login")
def login(
    email: str = typer.Option(..., prompt="Email"),
    password: str = typer.Option(..., prompt="Password", hide_input=True),
):
    """Login and save auth token."""
    try:
        data = _post("/auth/login", {"email": email, "password": password}, auth=False)
        _save_token(data["access_token"], data["role"], data["name"], data["user_id"])
        console.print(Panel(
            f"[green]✓ Logged in as [bold]{data['name']}[/bold][/green]\n"
            f"Role: {data['role']}\nUser ID: {data['user_id']}",
            title="Login Successful"
        ))
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Login failed: {e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("logout")
def logout():
    """Clear saved auth token."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
    console.print("[green]Logged out[/green]")


@app.command("place-order")
def place_order(
    pickup: str = typer.Option(..., prompt="Pickup address"),
    dropoff: str = typer.Option(..., prompt="Dropoff address"),
    description: str = typer.Option("", prompt="Package description"),
    amount: float = typer.Option(0.0, prompt="Amount (₱)"),
    notes: str = typer.Option("", prompt="Special notes"),
):
    """Place a new delivery order."""
    try:
        data = _post("/orders", {
            "pickup_address": pickup,
            "dropoff_address": dropoff,
            "package_desc": description or None,
            "total_amount": amount,
            "notes": notes or None,
        })
        console.print(Panel(
            f"[green]✓ Order #{data['id']} placed![/green]\n"
            f"Status: {data['status']}\n"
            f"Pickup: {data['pickup_address']}\n"
            f"Dropoff: {data['dropoff_address']}\n"
            f"Amount: ₱{data['total_amount']:.2f}",
            title="Order Created"
        ))
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("list-orders")
def list_orders():
    """List your orders."""
    try:
        orders = _get("/orders")
        if not orders:
            console.print("[yellow]No orders found[/yellow]")
            return

        table = Table(title="Orders", show_header=True)
        table.add_column("ID", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Pickup", max_width=25)
        table.add_column("Dropoff", max_width=25)
        table.add_column("Driver")
        table.add_column("Amount")
        table.add_column("Created")

        status_colors = {
            "pending": "yellow", "assigned": "blue",
            "picked_up": "magenta", "in_transit": "cyan",
            "delivered": "green", "cancelled": "red",
        }
        for o in orders:
            color = status_colors.get(o["status"], "white")
            table.add_row(
                str(o["id"]),
                f"[{color}]{o['status']}[/{color}]",
                o["pickup_address"][:25],
                o["dropoff_address"][:25],
                o.get("driver_name") or "-",
                f"₱{o['total_amount']:.2f}",
                str(o["created_at"])[:16],
            )
        console.print(table)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]{e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("track-order")
def track_order(order_id: int = typer.Argument(..., help="Order ID to track")):
    """Track a specific order."""
    try:
        o = _get(f"/orders/{order_id}")
        status_icon = {
            "pending": "⏳", "assigned": "👤", "picked_up": "📦",
            "in_transit": "🚚", "delivered": "✅", "cancelled": "❌",
        }.get(o["status"], "?")

        content = (
            f"{status_icon} Status: [bold]{o['status'].upper()}[/bold]\n"
            f"Customer: {o.get('customer_name', '-')}\n"
            f"Pickup: {o['pickup_address']}\n"
            f"Dropoff: {o['dropoff_address']}\n"
            f"Package: {o.get('package_desc') or 'N/A'}\n"
            f"Amount: ₱{o['total_amount']:.2f}\n"
            f"Driver: {o.get('driver_name') or 'Not assigned'}\n"
            f"Delivery Status: {o.get('delivery_status') or 'N/A'}\n"
            f"Created: {str(o['created_at'])[:16]}"
        )
        console.print(Panel(content, title=f"Order #{order_id}"))
    except httpx.HTTPStatusError as e:
        console.print(f"[red]{e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("list-drivers")
def list_drivers():
    """List all drivers (admin/any)."""
    try:
        drivers = _get("/drivers")
        if not drivers:
            console.print("[yellow]No drivers found[/yellow]")
            return

        table = Table(title="Drivers")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Vehicle")
        table.add_column("Status")
        table.add_column("Deliveries")
        table.add_column("Rating")

        for d in drivers:
            color = {"available": "green", "busy": "yellow", "offline": "red"}.get(d["availability_status"], "white")
            table.add_row(
                str(d["id"]), d["name"], d["vehicle_type"],
                f"[{color}]{d['availability_status']}[/{color}]",
                str(d["total_deliveries"]), str(d["rating"]),
            )
        console.print(table)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]{e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("assign-driver")
def assign_driver(
    order_id: int = typer.Argument(..., help="Order ID"),
    driver_id: int = typer.Argument(..., help="Driver ID"),
):
    """Assign a driver to an order (admin only)."""
    try:
        data = _post("/deliveries/assign", {"order_id": order_id, "driver_id": driver_id})
        console.print(f"[green]✓ {data['message']}[/green]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]{e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("auto-assign")
def auto_assign(order_id: int = typer.Argument(..., help="Order ID")):
    """Auto-assign best available driver (admin only)."""
    try:
        data = _get(f"/admin/auto-assign/{order_id}")
        console.print(f"[green]✓ {data['message']}[/green]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]{e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("update-status")
def update_status(
    delivery_id: int = typer.Argument(..., help="Delivery ID"),
    new_status: str = typer.Argument(..., help="New status: picked_up/in_transit/delivered/failed"),
    notes: str = typer.Option("", help="Driver notes"),
):
    """Update delivery status (driver only)."""
    try:
        data = _patch(f"/deliveries/{delivery_id}/status", {
            "new_status": new_status,
            "driver_notes": notes or None,
        })
        console.print(f"[green]✓ {data['message']}[/green]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]{e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("my-deliveries")
def my_deliveries():
    """List your assigned deliveries (driver)."""
    try:
        deliveries = _get("/deliveries/my")
        if not deliveries:
            console.print("[yellow]No deliveries found[/yellow]")
            return

        table = Table(title="My Deliveries")
        table.add_column("Delivery ID", style="cyan")
        table.add_column("Order ID")
        table.add_column("Status")
        table.add_column("Assigned At")
        table.add_column("Delivered At")

        for d in deliveries:
            color = {"assigned": "blue", "picked_up": "magenta", "in_transit": "cyan",
                     "delivered": "green", "failed": "red"}.get(d["status"], "white")
            table.add_row(
                str(d["id"]), str(d["order_id"]),
                f"[{color}]{d['status']}[/{color}]",
                str(d.get("assigned_at") or "")[:16],
                str(d.get("delivered_at") or "-")[:16],
            )
        console.print(table)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]{e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("analytics")
def analytics():
    """View system analytics (admin only)."""
    try:
        a = _get("/admin/analytics")
        console.print(Panel(
            f"[bold]Orders[/bold]\n"
            f"  Total: {a['total_orders']}\n"
            f"  Pending:    [yellow]{a['pending_orders']}[/yellow]\n"
            f"  Assigned:   [blue]{a['assigned_orders']}[/blue]\n"
            f"  In Transit: [cyan]{a['in_transit_orders']}[/cyan]\n"
            f"  Delivered:  [green]{a['delivered_orders']}[/green]\n"
            f"  Cancelled:  [red]{a['cancelled_orders']}[/red]\n\n"
            f"[bold]Drivers[/bold]\n"
            f"  Total:     {a['total_drivers']}\n"
            f"  Available: [green]{a['available_drivers']}[/green]\n"
            f"  Busy:      [yellow]{a['busy_drivers']}[/yellow]\n\n"
            f"[bold]Customers[/bold]: {a['total_customers']}\n"
            f"[bold]Avg Delivery Time[/bold]: "
            f"{a.get('avg_delivery_minutes') and f\"{a['avg_delivery_minutes']:.1f} min\" or 'N/A'}",
            title="System Analytics"
        ))
    except httpx.HTTPStatusError as e:
        console.print(f"[red]{e.response.json().get('detail')}[/red]")
        raise typer.Exit(1)


@app.command("simulate-full-flow")
def simulate_full_flow():
    """
    Simulates a complete order lifecycle:
    1. Create customer + driver + admin
    2. Login as customer → place order
    3. Login as admin → assign driver
    4. Login as driver → update status through lifecycle
    """
    import time

    console.print(Panel("[bold cyan]Starting Full Flow Simulation[/bold cyan]"))

    def register(name, email, pw, role, vehicle=None):
        try:
            r = httpx.post(f"{API_BASE}/auth/register", json={
                "name": name, "email": email, "password": pw,
                "role": role, "vehicle_type": vehicle or "motorcycle"
            })
            return r.json()
        except Exception:
            return None

    def do_login(email, pw):
        r = httpx.post(f"{API_BASE}/auth/login", json={"email": email, "password": pw})
        d = r.json()
        _save_token(d["access_token"], d["role"], d["name"], d["user_id"])
        return d

    import random
    suffix = random.randint(1000, 9999)

    # 1. Register users
    console.print("1️⃣  Registering users...")
    register(f"Test Customer {suffix}", f"customer{suffix}@test.com", "test1234", "customer")
    register(f"Test Driver {suffix}", f"driver{suffix}@test.com", "test1234", "driver")

    # 2. Customer places order
    console.print("2️⃣  Placing order as customer...")
    do_login(f"customer{suffix}@test.com", "test1234")
    order = _post("/orders", {
        "pickup_address": f"123 Market St, Manila",
        "dropoff_address": f"456 Rizal Ave, Quezon City",
        "package_desc": "Test package",
        "total_amount": 150.0,
    })
    order_id = order["id"]
    console.print(f"   ✓ Order #{order_id} placed")

    # 3. Admin assigns driver
    console.print("3️⃣  Admin assigning driver...")
    do_login("admin@delivery.com", "admin123")
    assign_resp = _get(f"/admin/auto-assign/{order_id}")
    delivery_id = assign_resp["delivery_id"]
    console.print(f"   ✓ Delivery #{delivery_id} created, driver assigned")

    # 4. Driver updates status
    console.print("4️⃣  Driver updating status...")
    do_login(f"driver{suffix}@test.com", "test1234")

    for status in ["picked_up", "in_transit", "delivered"]:
        time.sleep(0.5)
        _patch(f"/deliveries/{delivery_id}/status", {
            "new_status": status, "driver_notes": f"Status: {status}"
        })
        console.print(f"   ✓ → {status}")

    # 5. Verify final state
    console.print("5️⃣  Verifying final order state...")
    do_login("admin@delivery.com", "admin123")
    final = _get(f"/orders/{order_id}")
    console.print(Panel(
        f"Order #{order_id} final status: [green][bold]{final['status']}[/bold][/green]\n"
        f"Driver: {final.get('driver_name', 'N/A')}\n"
        f"Delivery Status: {final.get('delivery_status', 'N/A')}",
        title="[green]✅ Simulation Complete[/green]"
    ))


if __name__ == "__main__":
    app()
