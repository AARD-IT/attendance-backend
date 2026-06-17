"""
FastAPI application main file.
Initializes the FastAPI app with CORS middleware, routers, and health check endpoints.
"""

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.ceo import router as ceo_router
from app.api.employee import router as employee_router
from app.api.attendance import router as attendance_router
from app.api.minerva import router as minerva_router
from app.api.automation import router as automation_router
from app.api.minerva_sync import router as minerva_sync_router
from app.api.routes.dashboard import router as dashboard_router
from app.core.config import settings


# Create FastAPI application
app = FastAPI(
    title="Attendance Dashboard API - Phase 2",
    description="Phase 2: Attendance Backend Foundation",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoints
@app.get("/health", status_code=status.HTTP_200_OK, tags=["health"])
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Attendance Dashboard API",
        "version": "0.1.0"
    }


@app.get("/api/health", status_code=status.HTTP_200_OK, tags=["health"])
def api_health_check():
    """API health check endpoint."""
    return {
        "status": "ok",
        "message": "API is running"
    }


# Root endpoint
@app.get("/", tags=["root"])
def root():
    """Root endpoint with API info."""
    return {
        "message": "Attendance Dashboard API - Phase 2",
        "docs": "/api/docs",
        "version": "0.1.0"
    }


# Expose openapi.json at the server root for convenience (also available at /api/openapi.json)
@app.get("/openapi.json", include_in_schema=False)
def openapi_root():
    return app.openapi()


# Include routers (routers have their own prefixes defined)
app.include_router(auth_router)
app.include_router(ceo_router)
app.include_router(employee_router)
app.include_router(attendance_router)
app.include_router(minerva_router)
app.include_router(automation_router)
app.include_router(minerva_sync_router)
app.include_router(dashboard_router)


# Global exception handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 Not Found."""
    return JSONResponse(
        status_code=404,
        content={"detail": "Endpoint not found"}
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle 500 Internal Server Error."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

