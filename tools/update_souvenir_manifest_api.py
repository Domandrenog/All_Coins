#!/usr/bin/env python3
"""Atualiza na Base44 apenas os Souvenirs presentes num manifesto promovido."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "fotos" / "paises" / "America" / "EUA" / "souvenir" / "recortes-manifest.json"
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.souvenir_formats import SUPPORTED_SOUVENIR_TYPES  # noqa: E402
from scripts.sync_coin_images_api import (  # noqa: E402
    API_KEY_ENV,
    READ_ONLY_FIELDS,
    api_request,
    load_dotenv,
)


def load_manifest(
    path: Path,
    location_id: str | None,
    record_ids: set[str] | None = None,
) -> list[tuple[str, dict[str, object]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Manifesto em falta: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Manifesto inválido: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError("O manifesto deve ser um objeto indexado pelo ID da Base44.")
    rows = [
        (str(record_id), entry)
        for record_id, entry in data.items()
        if isinstance(entry, dict)
        and (location_id is None or str(entry.get("location_id")) == location_id)
        and (record_ids is None or str(record_id) in record_ids)
    ]
    rows.sort(key=lambda item: (int(item[1].get("machine") or 0), int(item[1].get("position") or 0)))
    if not rows:
        raise ValueError("O manifesto não contém registos no âmbito pedido.")
    if record_ids is not None:
        missing_ids = sorted(record_ids - {record_id for record_id, _ in rows})
        if missing_ids:
            raise ValueError(f"IDs pedidos em falta no manifesto: {', '.join(missing_ids)}")
    return rows


def desired_values(entry: dict[str, object]) -> tuple[str, str]:
    url = str(entry.get("internal_front") or "")
    orientation = str(entry.get("orientation") or "")
    if not url.startswith("https://raw.githubusercontent.com/"):
        raise ValueError(f"URL interno inválido: {url}")
    if orientation not in {"portrait", "landscape"}:
        raise ValueError(f"Orientação inválida: {orientation}")
    return url, orientation


def preflight(
    api_key: str,
    rows: list[tuple[str, dict[str, object]]],
) -> list[tuple[dict[str, object], dict[str, object]]]:
    prepared: list[tuple[dict[str, object], dict[str, object]]] = []
    for record_id, entry in rows:
        record = api_request("GET", f"/entities/Souvenir/{record_id}", api_key)
        if not isinstance(record, dict) or str(record.get("id")) != record_id:
            raise ValueError(f"Resposta inesperada para {record_id}.")
        expected_type = str(entry.get("type") or "pressed")
        if expected_type not in SUPPORTED_SOUVENIR_TYPES:
            raise ValueError(f"{record_id}: tipo não suportado no manifesto: {expected_type}.")
        if record.get("type") != expected_type:
            raise ValueError(
                f"{record_id}: tipo mudou desde o recorte; "
                f"esperado={expected_type!r}, atual={record.get('type')!r}."
            )
        target_url, _ = desired_values(entry)
        external_url = str(entry.get("external_front") or entry.get("source_url") or "")
        current_url = str(record.get("image_front") or "")
        if current_url not in {external_url, target_url}:
            raise ValueError(
                f"{record_id}: image_front mudou desde o recorte; atual={current_url!r}."
            )
        prepared.append((record, entry))
    return prepared


def difference_payload(
    record: dict[str, object],
    entry: dict[str, object],
) -> dict[str, object]:
    target_url, orientation = desired_values(entry)
    payload: dict[str, object] = {}
    if record.get("image_front") != target_url:
        payload["image_front"] = target_url
    if record.get("display_orientation") != orientation:
        payload["display_orientation"] = orientation
    return payload


def verify_partial_update(
    before: dict[str, object],
    after: dict[str, object],
    payload: dict[str, object],
) -> None:
    for field, expected in payload.items():
        if after.get(field) != expected:
            raise RuntimeError(f"A API não guardou o campo esperado: {field}")
    for field, value in before.items():
        if field in READ_ONLY_FIELDS or field in payload:
            continue
        if after.get(field) != value:
            raise RuntimeError(f"Campo alterado inesperadamente: {field}")


def apply_updates(
    api_key: str,
    prepared: list[tuple[dict[str, object], dict[str, object]]],
) -> tuple[int, int]:
    updated = 0
    unchanged = 0
    total = len(prepared)
    started = time.monotonic()
    for index, (before, entry) in enumerate(prepared, 1):
        payload = difference_payload(before, entry)
        if not payload:
            unchanged += 1
            print(f"✓ [{index}/{total}] já atualizado — {before.get('name') or before['id']}")
            continue
        record_id = str(before["id"])
        api_request("PUT", f"/entities/Souvenir/{record_id}", api_key, payload=payload)
        after = api_request("GET", f"/entities/Souvenir/{record_id}", api_key)
        if not isinstance(after, dict):
            raise RuntimeError(f"Resposta inesperada ao verificar {record_id}.")
        verify_partial_update(before, after, payload)
        updated += 1
        elapsed = time.monotonic() - started
        average = elapsed / index
        eta = average * (total - index)
        print(
            f"✓ [{index}/{total} | {index / total * 100:.0f}% | "
            f"decorrido {elapsed:.0f}s | ETA {eta:.0f}s] "
            f"{before.get('name') or record_id} — campos: {', '.join(payload)}"
        )
    return updated, unchanged


def verify_all(
    api_key: str,
    prepared: list[tuple[dict[str, object], dict[str, object]]],
) -> None:
    for before, entry in prepared:
        record_id = str(before["id"])
        current = api_request("GET", f"/entities/Souvenir/{record_id}", api_key)
        target_url, orientation = desired_values(entry)
        if not isinstance(current, dict):
            raise RuntimeError(f"Resposta inesperada na validação final de {record_id}.")
        if current.get("image_front") != target_url:
            raise RuntimeError(f"{record_id}: URL final incorreto.")
        if current.get("display_orientation") != orientation:
            raise RuntimeError(f"{record_id}: orientação final incorreta.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--location-id")
    parser.add_argument("--record-id", action="append", dest="record_ids", help="Limita a atualização a um ID concluído; pode repetir-se.")
    parser.add_argument("--api-key-env", default=API_KEY_ENV)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Define {args.api_key_env} no ficheiro .env.", file=sys.stderr)
        return 2
    try:
        rows = load_manifest(
            args.manifest.resolve(),
            args.location_id,
            set(args.record_ids) if args.record_ids else None,
        )
        prepared = preflight(api_key, rows)
        differences = [
            (record, difference_payload(record, entry))
            for record, entry in prepared
            if difference_payload(record, entry)
        ]
        print(
            f"Pré-verificação concluída: {len(prepared)} registos; "
            f"{len(differences)} pendentes."
        )
        for record, payload in differences:
            print(
                f"- {record.get('name') or record['id']} ({record['id']}): "
                f"{', '.join(payload)}"
            )
        if not args.apply:
            print("Dry-run concluído; a Base44 não foi alterada.")
            return 0
        updated, unchanged = apply_updates(api_key, prepared)
        verify_all(api_key, prepared)
        print(
            f"Validação final concluída: {len(prepared)}/{len(prepared)} corretos "
            f"({updated} atualizados, {unchanged} já corretos)."
        )
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
