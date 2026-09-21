#!/usr/bin/env python3
"""Verifica imagens ainda externas nas categorias collection e notes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

try:
    from .sync_coin_images_api import DEFAULT_RAW_BASE_URL, api_request, load_dotenv
except ImportError:
    from sync_coin_images_api import DEFAULT_RAW_BASE_URL, api_request, load_dotenv


CATALOGS = {
    "collection": {"entity": "SpecialCoin", "year_field": "year"},
    "notes": {"entity": "CountryNote", "year_field": "year"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verifica imagens externas por categoria na API.")
    parser.add_argument("--catalog", choices=sorted(CATALOGS), required=True)
    parser.add_argument("--country", help="Filtra um país específico.")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--api-key-env", default="ALL_COINS_API_KEY")
    parser.add_argument("--raw-base-url", default=DEFAULT_RAW_BASE_URL)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def list_records(api_key: str, args: argparse.Namespace) -> list[dict[str, object]]:
    config = CATALOGS[args.catalog]
    query: dict[str, object] = {"limit": args.limit}
    if args.country:
        query["q"] = json.dumps({"country": args.country}, ensure_ascii=False)
    data = api_request("GET", f"/entities/{config['entity']}", api_key, query=query)
    if not isinstance(data, list):
        raise RuntimeError(f"Resposta inesperada ao listar {config['entity']}: {data!r}")
    return [row for row in data if isinstance(row, dict)]


def is_internal(url: object, raw_base_url: str, catalog: str) -> bool:
    value = str(url or "")
    return value.startswith(raw_base_url.rstrip("/") + "/") and f"/{catalog}/" in value


def build_report(
    records: list[dict[str, object]], catalog: str, raw_base_url: str
) -> dict[str, object]:
    year_field = str(CATALOGS[catalog]["year_field"])
    country_totals: dict[str, int] = defaultdict(int)
    pending: dict[str, list[dict[str, object]]] = defaultdict(list)
    partial: dict[str, list[dict[str, object]]] = defaultdict(list)
    missing: dict[str, list[dict[str, object]]] = defaultdict(list)

    for record in records:
        country = str(record.get("country") or "(sem país)")
        country_totals[country] += 1
        front = str(record.get("image_frente") or "").strip()
        back = str(record.get("image_verso") or "").strip()
        front_internal = is_internal(front, raw_base_url, catalog)
        back_internal = is_internal(back, raw_base_url, catalog)
        row = {
            "id": record.get("id"),
            "name": record.get("name"),
            "year": record.get(year_field),
            "internal_sides": [
                side
                for side, present in (("frente", front_internal), ("verso", back_internal))
                if present
            ],
        }

        if not front or not back:
            missing[country].append(row)
        elif front_internal != back_internal:
            partial[country].append(row)
        elif not (front_internal and back_internal):
            pending[country].append(row)

    return {
        "catalog": catalog,
        "total_records": len(records),
        "countries": len(country_totals),
        "records_internal": sum(
            is_internal(row.get("image_frente"), raw_base_url, catalog)
            and is_internal(row.get("image_verso"), raw_base_url, catalog)
            for row in records
        ),
        "records_pending": sum(len(rows) for rows in pending.values()),
        "records_partial": sum(len(rows) for rows in partial.values()),
        "records_missing": sum(len(rows) for rows in missing.values()),
        "pending_by_country": dict(sorted(pending.items())),
        "partial_by_country": dict(sorted(partial.items())),
        "missing_by_country": dict(sorted(missing.items())),
        "country_totals": dict(sorted(country_totals.items())),
    }


def print_report(report: dict[str, object]) -> None:
    for field in (
        "catalog",
        "total_records",
        "countries",
        "records_internal",
        "records_pending",
        "records_partial",
        "records_missing",
    ):
        print(f"{field}={report[field]}")

    pending = report["pending_by_country"]
    partial = report["partial_by_country"]
    missing = report["missing_by_country"]
    assert isinstance(pending, dict)
    assert isinstance(partial, dict)
    assert isinstance(missing, dict)

    for heading, groups in (
        ("Imagens externas pendentes", pending),
        ("Pares parcialmente migrados", partial),
        ("Registos com imagens em falta", missing),
    ):
        if not groups:
            continue
        print(f"\n{heading}")
        for country, rows in groups.items():
            print(f"{country}: {len(rows)}")
            for row in rows:
                print(f"  - {row['name']} | {row['year']} | {row['id']}")

    if not pending and not partial and not missing:
        print("\nOK: todos os pares de imagens desta categoria apontam para o repositório.")


def main() -> int:
    args = parse_args()
    load_dotenv()
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Define {args.api_key_env} no ficheiro .env.", file=sys.stderr)
        return 2
    records = list_records(api_key, args)
    report = build_report(records, args.catalog, args.raw_base_url)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 1 if report["records_pending"] or report["records_partial"] or report["records_missing"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
