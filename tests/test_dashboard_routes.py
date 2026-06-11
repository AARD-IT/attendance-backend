from app.main import app


def test_employee_monthly_attendance_route_is_registered():
    routes = {route.path for route in app.routes}

    assert "/api/v1/employees/{employee_id}/attendance" in routes
