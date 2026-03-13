"""Pydantic schemas for report generation, preview, download, and exchange import endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReportGenerateRequest(BaseModel):
    """Request body for POST /api/reports/generate."""

    year: int = Field(..., ge=2000, le=2100, description="Tax year for report generation")
    tax_treatment: str = Field(
        default="capital",
        description="Tax treatment: 'capital' or 'business'",
    )
    specialist_override: bool = Field(
        default=False,
        description="Skip needs_review gate. Admin-only.",
    )


class ReportGenerateResponse(BaseModel):
    """Response for POST /api/reports/generate."""

    job_id: int
    status: str  # always "queued" on creation


class ReportPreviewResponse(BaseModel):
    """Response for GET /api/reports/preview/{report_type}."""

    report_type: str
    rows: List[Dict[str, Any]]
    total: int


class ReportFileInfo(BaseModel):
    """Metadata for a single report file."""

    name: str
    size: int
    url: str


class ReportFileResponse(BaseModel):
    """Response for GET /api/reports/download/{year} (file listing)."""

    year: int
    files: List[ReportFileInfo]
    generated_at: Optional[str] = None


class ReportStatusResponse(BaseModel):
    """Response for GET /api/reports/status."""

    year: int
    exists: bool
    file_count: int = 0


class ExchangeImportResponse(BaseModel):
    """Response for POST /api/exchanges/import."""

    job_id: int
    file_import_id: int
    status: str = "queued"


class SupportedExchange(BaseModel):
    """A supported exchange entry."""

    slug: str
    name: str
    accepts_csv: bool = True
