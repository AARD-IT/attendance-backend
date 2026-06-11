import csv
import io
import zipfile
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.middleware.auth import require_ceo
from app.models.profile import Profile
from app.services.dashboard_analytics_service import analytics_service

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/summary", status_code=status.HTTP_200_OK)
def get_dashboard_summary(month: int | None = Query(default=None), year: int | None = Query(default=None), _current_user: Profile = Depends(require_ceo)):
    return analytics_service.get_summary(month=month, year=year)


@router.get("/dashboard/trends", status_code=status.HTTP_200_OK)
def get_dashboard_trends(month: int | None = Query(default=None), year: int | None = Query(default=None), _current_user: Profile = Depends(require_ceo)):
    return analytics_service.get_trends(month=month, year=year)


@router.get("/dashboard/departments", status_code=status.HTTP_200_OK)
def get_department_analytics(_current_user: Profile = Depends(require_ceo)):
    return analytics_service.get_departments()


@router.get("/dashboard/employees", status_code=status.HTTP_200_OK)
def get_employee_attendance_table(month: int | None = Query(default=None), year: int | None = Query(default=None), _current_user: Profile = Depends(require_ceo)):
    return analytics_service.get_employees(month=month, year=year)


@router.get("/dashboard/working-hours", status_code=status.HTTP_200_OK)
def get_working_hours_chart(month: int | None = Query(default=None), year: int | None = Query(default=None), _current_user: Profile = Depends(require_ceo)):
    return analytics_service.get_working_hours(month=month, year=year)


@router.get("/dashboard/employees/{employee_id}", status_code=status.HTTP_200_OK)
def get_employee_detail(employee_id: str, month: int | None = Query(default=None), year: int | None = Query(default=None), _current_user: Profile = Depends(require_ceo)):
    return analytics_service.get_employee_detail(employee_id, month=month, year=year)


@router.get("/v1/employees/{employee_id}/attendance", status_code=status.HTTP_200_OK)
def get_employee_monthly_attendance(employee_id: str, month: int | None = Query(default=None), year: int | None = Query(default=None), _current_user: Profile = Depends(require_ceo)):
    return analytics_service.get_employee_monthly_attendance(employee_id, month=month, year=year)


@router.get("/dashboard/live", status_code=status.HTTP_200_OK)
def get_live_attendance_feed(month: int | None = Query(default=None), year: int | None = Query(default=None), _current_user: Profile = Depends(require_ceo)):
    return analytics_service.get_live_feed(month=month, year=year)


@router.get("/reports/csv", status_code=status.HTTP_200_OK)
def export_csv(_current_user: Profile = Depends(require_ceo)):
    rows = analytics_service.get_employees()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee Name", "Employee Code", "Department", "Status", "Check In", "Check Out", "Working Hours"])
    for row in rows:
        writer.writerow([row.get("employee_name"), row.get("employee_code"), row.get("department"), row.get("status"), row.get("check_in"), row.get("check_out"), row.get("working_hours")])

    return StreamingResponse(iter([output.getvalue().encode("utf-8")]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=attendance_report.csv"})


@router.get("/reports/excel", status_code=status.HTTP_200_OK)
def export_excel(_current_user: Profile = Depends(require_ceo)):
    rows = analytics_service.get_employees()
    output = io.BytesIO()

    def escape_xml(value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    sheet_rows = [
        "<row>",
        "<c t=\"inlineStr\"><is><t>Employee Name</t></is></c>",
        "<c t=\"inlineStr\"><is><t>Employee Code</t></is></c>",
        "<c t=\"inlineStr\"><is><t>Department</t></is></c>",
        "<c t=\"inlineStr\"><is><t>Status</t></is></c>",
        "<c t=\"inlineStr\"><is><t>Check In</t></is></c>",
        "<c t=\"inlineStr\"><is><t>Check Out</t></is></c>",
        "<c t=\"inlineStr\"><is><t>Working Hours</t></is></c>",
        "</row>",
    ]

    for row in rows:
        sheet_rows.append("<row>")
        for value in [row.get("employee_name"), row.get("employee_code"), row.get("department"), row.get("status"), row.get("check_in"), row.get("check_out"), row.get("working_hours")]:
            sheet_rows.append(f"<c t=\"inlineStr\"><is><t>{escape_xml(str(value))}</t></is></c>")
        sheet_rows.append("</row>")

    sheet_xml = "".join(sheet_rows)
    with zipfile.ZipFile(output, "w") as workbook:
        workbook.writestr("[Content_Types].xml", """<?xml version=\"1.0\" encoding=\"UTF-8\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/><Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/><Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/><Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/></Types>""")
        workbook.writestr("_rels/.rels", """<?xml version=\"1.0\" encoding=\"UTF-8\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/><Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/></Relationships>""")
        workbook.writestr("docProps/app.xml", """<?xml version=\"1.0\" encoding=\"UTF-8\"?><Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\"><Application>Attendance Dashboard</Application></Properties>""")
        workbook.writestr("docProps/core.xml", """<?xml version=\"1.0\" encoding=\"UTF-8\"?><cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\" xmlns:dcterms=\"http://purl.org/dc/terms/\" xmlns:dcmitype=\"http://purl.org/dc/dcmitype\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"><dc:title>Attendance Report</dc:title><dc:creator>Attendance Dashboard</dc:creator></cp:coreProperties>""")
        workbook.writestr("xl/workbook.xml", """<?xml version=\"1.0\" encoding=\"UTF-8\"?><workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheets><sheet name=\"Attendance\" sheetId=\"1\" r:id=\"rId1\"/></sheets></workbook>""")
        workbook.writestr("xl/_rels/workbook.xml.rels", """<?xml version=\"1.0\" encoding=\"UTF-8\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/></Relationships>""")
        workbook.writestr("xl/worksheets/sheet1.xml", f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?><worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>{sheet_xml}</sheetData></worksheet>""")

    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=attendance_report.xlsx"})


@router.get("/reports/pdf", status_code=status.HTTP_200_OK)
def export_pdf(_current_user: Profile = Depends(require_ceo)):
    rows = analytics_service.get_employees()[:10]
    lines = ["Attendance Report", ""]
    for row in rows:
        lines.append(f"{row.get('employee_name')} | {row.get('status')} | {row.get('check_in')} - {row.get('check_out')} | {row.get('working_hours')}h")
    content = "\n".join(lines)
    escaped = content.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    pdf = "%PDF-1.4\n"
    objects = []
    objects.append("1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append("2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append("3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>endobj\n")
    objects.append("4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    objects.append(f"5 0 obj<< /Length {len(escaped.encode('latin-1'))} >>stream\nBT /F1 11 Tf 50 760 Td ({escaped}) Tj ET\nendstream\nendobj\n")

    pdf += "".join(objects)
    startxref = len(pdf.encode('latin-1'))
    xref = ["xref\n", "0 6\n", "0000000000 65535 f \n"]
    offset = 0
    for obj in objects:
        xref.append(f"{offset:010d} 00000 n \n")
        offset += len(obj.encode('latin-1'))
    pdf += "".join(xref)
    pdf += f"trailer<< /Size 6 /Root 1 0 R >>\nstartxref {startxref}\n%%EOF"
    return StreamingResponse(iter([pdf.encode("latin-1")]), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=attendance_report.pdf"})
