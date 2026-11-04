#!/usr/bin/env python3
"""Generate a traceable inventory from the release master-plan Markdown."""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

CASE_HEADING = re.compile(r"^####\s+([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d{3})\s+[—–-]\s+(.+?)\s*$")
ROUTE_ROW = re.compile(r"^\|\s*(WEB-ROUTE-\d{3})\s*\|")
PRIORITY = re.compile(r"\b(P[0-3])\b", re.IGNORECASE)
LABELED_PRIORITY = re.compile(
    r"(?:\*\*[^*]*(?:prioridad|priority)[^*]*\*\*|(?:prioridad|priority)\s*:)"
    r"[^\n]*?\b(P[0-3])\b",
    re.IGNORECASE,
)
COMPOSITE_PRIORITY = re.compile(
    r"\*\*Área / prioridad / tipo / nivel:\*\*.*?\b(P[0-3])\b", re.IGNORECASE
)
KIND = re.compile(r"\*\*(?:Tipo|Type):\*\*\s*`?([AMH])\b", re.IGNORECASE)
GENERIC_KIND = re.compile(r"(?:;\s*`|;\s*|\bP[0-3]\s*/\s*)([AMH])\b", re.IGNORECASE)
OWNER = re.compile(
    r"(?:\*\*)?(?:Owner|Responsable)(?:\s+lógico)?\s*:(?:\*\*)?\s*"
    r"(?:`([^`]+)`|([^.;]+))",
    re.IGNORECASE,
)
STATUS = re.compile(
    r"(?:\*\*)?(?:Estado(?: en esta tarea)?|Status)\s*:(?:\*\*)?\s*`?([^`;.\n]+)",
    re.IGNORECASE,
)
ACCEPTANCE_LABEL = re.compile(
    r"\*\*(?P<label>[^*]*(?:\bPASS\b|criterio de aceptación|resultado esperado|"
    r"gate/aceptaci[oó]n)[^*]*)\*\*\s*"
    r"(?P<value>.*?)(?=\s+\*\*(?:FAIL\b|Evidencias?\b|Evidence\b|Comandos?\b|"
    r"Command\b|Limpieza\b|Cleanup\b)[^*]*\*\*|$)",
    re.IGNORECASE | re.DOTALL,
)
AREA = re.compile(
    r"\*\*(?:Área / prioridad / tipo / nivel|Categoría/feature|Area|Feature):\*\*\s*([^.;]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Case:
    case_id: str
    title: str
    section: str
    source_line: int
    area: str
    priority: str
    kind: str
    owner: str
    status: str
    acceptance: str
    family: str
    scope: str
    environment: str


PUBLIC_FAMILIES = "P1–P8, P10–P14"
PRO_ONLY = {
    "IAM-003",
    "IAM-004",
    "RG-SEC-002",
    "RG-SEC-003",
    "RG-SEC-004",
    "RG-SEC-005",
    "RG-SEC-016",
    "RG-HELM-001",
    "RG-SCH-PG-001",
}
GENAI_ONLY = {"AI-001", "AI-002", "AI-003", "RG-API-014"}

PREFIX_FAMILIES = {
    "AI": "P10 semantic models and dashboards",
    "API": f"Cross-cutting {PUBLIC_FAMILIES}",
    "CORE": "P14; execution primitives shared with P1/P5",
    "DATA": "P2/P3/P4",
    "GRAPH": "P6",
    "IAM": "P1/P13",
    "ML": "P8 (classical ML)",
    "OBS": "P11/P12",
    "PORT": "P2/P3/P14",
    "QUALITY": "P7",
    "REL": "P14; candidate-wide release gates",
    "RTEST": "P14; candidate-wide test tooling",
    "SCHED": "P5",
    "SEC": "P13",
    "STORAGE": "Cross-cutting P1/P5/P6/P8/P13/P14",
    "WEB": f"Cross-cutting {PUBLIC_FAMILIES}",
}

PREFIX_START_FAMILIES = (
    ("RG-AI-PRODUCT-BOUNDARY", "P13 scope-boundary regression"),
    ("RG-AGENT", "External coding-agent skills; no in-product runtime"),
    ("RG-A11Y", f"Cross-cutting UI ({PUBLIC_FAMILIES})"),
    ("RG-API", f"Cross-cutting {PUBLIC_FAMILIES}"),
    ("RG-BUNDLE", "P1/P6/P8/P10/P14; bundle and portability"),
    ("RG-CI", "P14 local quality gate; no CI"),
    ("RG-CONN", "P2 connectors and ingestion"),
    ("RG-DE", "P4 Data Engineering"),
    ("RG-DR", "P14 recovery and local operations"),
    ("RG-FIN", "P12 FinOps"),
    ("RG-GRAPH", "P6 graph intelligence"),
    ("RG-HELM", "P14 deployment profile; single-node only"),
    ("RG-LAKE", "P3 lakehouse"),
    ("RG-ML", "P8 classical ML"),
    ("RG-OBS", "P12 observability"),
    ("RG-OL", "P4/P12 lineage and observability"),
    ("RG-ONTO", "P6 ontology and catalog"),
    ("RG-OTLP", "P12 observability"),
    ("RG-PERF", f"Cross-cutting {PUBLIC_FAMILIES}"),
    ("RG-PG-BUNDLE", "P1/P14 project bundles and storage"),
    ("RG-PKG", "P14 packaging and installation"),
    ("RG-QUAL", "P14 local qualification tooling"),
    ("RG-REL", "P14 candidate-wide release gates"),
    ("RG-RQL", "P6 graph query language"),
    ("RG-RUNTIME", "P14 local runtime and worker"),
    ("RG-SCH", "P5 scheduler"),
    ("RG-SCOPE", "P13 public-scope controls"),
    ("RG-SEC", "P13 single-operator security"),
    ("RG-SEM", "P10 semantic models and dashboards"),
    ("RG-SQL", "P3 SQL and lakehouse"),
    ("RG-STR-PORT", "P11/P14 streaming portability"),
    ("RG-STR", "P11 streaming"),
    ("RG-STUDIO-GATE", f"Cross-cutting Studio ({PUBLIC_FAMILIES})"),
    ("RG-SYN", "P2/P7 synthetic data workflows and validation"),
    ("RG-UI", f"Cross-cutting UI ({PUBLIC_FAMILIES})"),
    ("RG-UPG", "P14 upgrade and recovery"),
    ("RG-UX-OBS", "P12 observability UX"),
    ("RG-UX-SYN", "P2/P7 synthetic data UX"),
    ("RG-UX", f"Cross-cutting UI ({PUBLIC_FAMILIES})"),
    ("RG-WEB", f"Cross-cutting Studio ({PUBLIC_FAMILIES})"),
)

FAMILY_ENVIRONMENTS = {
    "P1": "Isolated workspace/project, Git and bundle fixtures where specified",
    "P2": "PostgreSQL plus connector-specific service only for retained claims",
    "P3": "Parquet/DuckDB; optional SQL engines only for retained claims",
    "P4": "Installed Studio and executable notebook/pipeline worker",
    "P5": "PostgreSQL and worker; synthetic scheduler/event endpoints as specified",
    "P6": "SQLite/PostgreSQL and bounded graph/catalog fixtures",
    "P7": "Bounded SQL/Python checks and live quality API where required",
    "P8": "Classical ML extra; PostgreSQL/artifact store only for retained path",
    "P10": "Semantic Studio, SQL backend, browser and exported bundle fixtures",
    "P11": "Real Kafka-compatible broker, topic and durable checkpoint store",
    "P12": "Metrics/alert backend and synthetic notification endpoints when specified",
    "P13": "Single-operator auth, secret canaries, audit and security tooling",
    "P14": "Local Docker/Compose; optional packaging/Helm/provider tools per claim",
}


def _cell(value: str) -> str:
    return value.strip().replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def _field(pattern: re.Pattern[str], text: str, default: str = "N/D") -> str:
    match = pattern.search(text)
    if not match:
        return default
    value = next((group for group in match.groups() if group is not None), None)
    return value.strip() if value else default


def _kind(text: str) -> str:
    return _field(KIND, text, _field(GENERIC_KIND, text))


def _metadata(body: str) -> str:
    for line in body.splitlines()[:12]:
        if re.search(
            r"(?:área|area|feature|prioridad|priority|tipo:|type:|owner|responsable|estado|status)",
            line,
            re.IGNORECASE,
        ):
            return line
    return ""


def _priority(text: str) -> str:
    return _field(LABELED_PRIORITY, text, _field(COMPOSITE_PRIORITY, text))


def _acceptance(text: str) -> str:
    match = ACCEPTANCE_LABEL.search(text)
    if not match:
        return "N/D"
    return re.sub(r"\s+", " ", match.group("value")).strip() or "N/D"


def classify_case(case_id: str) -> tuple[str, str, str]:
    if case_id in GENAI_ONLY:
        family = "P9 retired; boundary regression only"
        scope = "Out of scope as a capability; verify absence only"
        environment = "No model/provider/agent runtime; offline boundary checks"
    elif case_id in PRO_ONLY:
        family = "Ronin Pro; multi-user or multi-replica profile"
        scope = "Out of Public v1; verify unsupported surface stays absent"
        environment = "No Pro identity, tenant or HA acceptance fixtures"
    elif case_id == "REL-001" or case_id.startswith("RG-CI"):
        family = "P14 local quality evidence"
        scope = "Replace CI-specific execution with equivalent local receipt"
        environment = "Local pinned toolchain; no CI workflow"
    else:
        parts = case_id.split("-")
        prefix = "-".join(parts[:-1])
        family = PREFIX_FAMILIES.get(prefix, "")
        if not family:
            family = next(
                (value for known, value in PREFIX_START_FAMILIES if prefix.startswith(known)),
                "Unmapped — manual triage required",
            )
        scope = "Active/shared candidate requirement; this mapping is not PASS evidence"
        if family.startswith("Cross-cutting"):
            environment = "Live local app/API; case-specific provider fixtures only when required"
        else:
            family_ids = re.findall(r"P(?:[1-8]|1[0-4])", family)
            environments = list(
                dict.fromkeys(
                    FAMILY_ENVIRONMENTS[item] for item in family_ids if item in FAMILY_ENVIRONMENTS
                )
            )
            environment = "; ".join(environments) or (
                "Use exact case preconditions; manual mapping required"
            )
    return family, scope, environment


def parse_cases(lines: list[str]) -> list[Case]:
    found: list[tuple[int, str, str, str]] = []
    section = "Documento"
    for index, line in enumerate(lines):
        if line.startswith("## "):
            section = line[3:].strip()
        match = CASE_HEADING.match(line)
        if match:
            found.append((index, match.group(1), match.group(2), section))

    ids = [case_id for _, case_id, _, _ in found]
    duplicates = sorted(case_id for case_id, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate case IDs: {', '.join(duplicates)}")

    cases: list[Case] = []
    for position, (index, case_id, title, section) in enumerate(found):
        end = found[position + 1][0] if position + 1 < len(found) else len(lines)
        body = "\n".join(lines[index + 1 : end])
        metadata = _metadata(body)
        family, scope, environment = classify_case(case_id)
        cases.append(
            Case(
                case_id=case_id,
                title=title,
                section=section,
                source_line=index + 1,
                area=_field(AREA, metadata),
                priority=_priority(metadata),
                kind=_kind(metadata),
                owner=_field(OWNER, metadata),
                status=_field(STATUS, metadata),
                acceptance=_acceptance(body),
                family=family,
                scope=scope,
                environment=environment,
            )
        )
    return cases


def parse_routes(lines: list[str]) -> list[tuple[str, str, str, str]]:
    routes: list[tuple[str, str, str, str]] = []
    for index, line in enumerate(lines):
        if not ROUTE_ROW.match(line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            raise ValueError(f"Malformed route row on source line {index + 1}")
        route_id = cells[0]
        route_match = re.search(r"`([^`]+)`", cells[1])
        if not route_match:
            raise ValueError(f"Missing route name on source line {index + 1}")
        route = route_match.group(1)
        retired = "retirada" in cells[1].lower() or "out_of_scope" in " ".join(cells).lower()
        status = "retirada" if retired else "activa"
        disposition = (
            "Regresión negativa: verificar que la superficie retirada no se anuncia"
            if retired
            else "Cualificar navegación y operación con API real"
        )
        routes.append((route_id, route, status, disposition))
    route_ids = [route_id for route_id, _, _, _ in routes]
    if len(route_ids) != len(set(route_ids)):
        raise ValueError("Duplicate WEB-ROUTE IDs in the source")
    return routes


def render_inventory(source: Path, output: Path) -> tuple[str, int, int, int]:
    raw = source.read_bytes()
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    cases = parse_cases(lines)
    routes = parse_routes(lines)
    digest = hashlib.sha256(raw).hexdigest()
    active_routes = sum(status == "activa" for _, _, status, _ in routes)
    classified_cases = sum(not case.family.startswith("Unmapped") for case in cases)
    cases_with_acceptance = sum(case.acceptance != "N/D" for case in cases)
    explicit_metadata = {
        field: sum(getattr(case, field) != "N/D" for case in cases)
        for field in ("priority", "kind", "owner", "status")
    }

    result = [
        "# Inventario reconciliado de casos de release — 29/10/2026",
        "",
        f"Fuente canónica: `{source.name}` (SHA-256 `{digest}`). "
        "Generado desde encabezados de caso y tabla de rutas; no reenumera el documento fuente.",
        "",
        "## Conteo verificado",
        "",
        f"- IDs únicos en todo el documento: **{len(cases)}**.",
        f"- Rutas históricas: **{len(routes)}**; activas: **{active_routes}**; "
        f"retiradas: **{len(routes) - active_routes}**.",
        f"- Disposición de familia/scope: **{classified_cases}/{len(cases)}** "
        "IDs mapeados por grupo; el mapeo requiere revisión del mantenedor/QA.",
        f"- Criterio PASS explícito extraído del maestro: "
        f"**{cases_with_acceptance}/{len(cases)}** fichas.",
        "- Metadatos presentes explícitamente en el maestro: "
        f"prioridad **{explicit_metadata['priority']}/{len(cases)}**, "
        f"tipo **{explicit_metadata['kind']}/{len(cases)}**, "
        f"owner **{explicit_metadata['owner']}/{len(cases)}**, "
        f"estado **{explicit_metadata['status']}/{len(cases)}**.",
        "- El conteo describe el catálogo del plan, no ejecución ni qualification. "
        "`N/D` significa que el campo no estaba etiquetado en la fuente.",
        "",
        "## Disposiciones vinculantes de alcance",
        "",
        "- GenAI/RAG/agentes: no ejecutar casos de capacidad como funcionalidades; "
        "mantener regresiones que comprueban su ausencia y las skills externas.",
        "- Ronin Pro: no cualificar multiusuario como capacidad de Public v1; validar "
        "que no se anuncie ni exponga en el perfil público.",
        "- Sin CI: resolver pasos de CI mediante comprobaciones locales reproducibles; "
        "no crear workflows ni relajar criterios.",
        "- Skills: validan paquetes portables para coding agents externos; no añaden "
        "inferencia, RAG ni runtime dentro de Ronin.",
        "- Prioridad, tipo, responsable y estado se copian solo cuando aparecen "
        "etiquetados en la fuente. Ninguna fila afirma PASS.",
        "- Familia/scope e infraestructura son asignaciones de triaje por ID; "
        "la precondición exacta del caso gobierna; los bloqueos y aprobaciones "
        "humanas siguen abiertos.",
        "",
        "## Matriz de rutas históricas",
        "",
        "| ID | Ruta | Estado | Disposición |",
        "|---|---|---|---|",
    ]
    for route_id, route, status, disposition in routes:
        result.append(f"| {route_id} | {_cell(route)} | {status} | {_cell(disposition)} |")
    result.extend(
        [
            "",
            f"## Catálogo íntegro de {len(cases)} fichas",
            "",
            "| ID | Section | Title | Area | P | Type | Owner | Status | PASS criterion | "
            "Family | Scope | Environment | Line |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---:|",
        ]
    )
    for case in cases:
        result.append(
            "| "
            + " | ".join(
                _cell(value)
                for value in (
                    case.case_id,
                    case.section,
                    case.title,
                    case.area,
                    case.priority,
                    case.kind,
                    case.owner,
                    case.status,
                    case.acceptance,
                    case.family,
                    case.scope,
                    case.environment,
                    str(case.source_line),
                )
            )
            + " |"
        )
    result.append("")
    output_text = "\n".join(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(output_text, encoding="utf-8", newline="\n")
    return output_text, len(cases), len(routes), active_routes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Canonical master plan")
    parser.add_argument("--output", required=True, type=Path, help="Inventory Markdown path")
    parser.add_argument(
        "--expected-cases", type=int, help="Fail unless this many unique cases are found"
    )
    parser.add_argument(
        "--expected-routes", type=int, help="Fail unless this many route IDs are found"
    )
    args = parser.parse_args()
    _, case_count, route_count, active_count = render_inventory(args.source, args.output)
    if args.expected_cases is not None and case_count != args.expected_cases:
        parser.error(f"expected {args.expected_cases} cases, found {case_count}")
    if args.expected_routes is not None and route_count != args.expected_routes:
        parser.error(f"expected {args.expected_routes} routes, found {route_count}")
    print(
        f"Generated {args.output}: {case_count} cases, {route_count} route IDs "
        f"({active_count} active)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
