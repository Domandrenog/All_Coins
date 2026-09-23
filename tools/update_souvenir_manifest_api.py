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

from scripts.sync_catalog_images_api import mutable_payload, verify_preserved_record  # noqa: E402
from scripts.sync_coin_images_api import API_KEY_ENV, api_request, load_dotenv  # noqa: E402


def load_manifest(path: Path, location_id: str | None) -> list[tuple[str, dict[str, object]]]:
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
    ]
    rows.sort(key=lambda item: (int(item[1].get("machine") or 0), int(item[1].get("position") or 0)))
    if not rows:
        raise ValueError("O manifesto não contém registos no âmbito pedido.")
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
        if record.get("type") != "pressed":
            raise ValueError(f"{record_id}: deixou de ser uma prensada.")
        target_url, _ = desired_values(entry)
        external_url = str(entry.get("external_front") or entry.get("source_url") or "")
        current_url = str(record.get("image_front") or "")
        if current_url not in {external_url, target_url}:
            raise ValueError(
                f"{record_id}: image_front mudou desde o recorte; atual={current_url!r}."
            )
        prepared.append((record, entry))
    return prepared


def apply_updates(
    api_key: str,
    prepared: list[tuple[dict[str, object], dict[str, object]]],
) -> tuple[int, int]:
    updated = 0
    unchanged = 0
    total = len(prepared)
    started = time.monotonic()
    for index, (before, entry) in enumerate(prepared, 1):
        target_url, orientation = desired_values(entry)
        if (
            before.get("image_front") == target_url
            and before.get("display_orientation") == orientation
        ):
            unchanged += 1
            print(f"✓ [{index}/{total}] já atualizado — {before.get('name') or before['id']}")
            continue
        back_url = str(before.get("image_back") or "")
        payload = mutable_payload(before, "souvenir", target_url, back_url, orientation)
        record_id = str(before["id"])
        api_request("PUT", f"/entities/Souvenir/{record_id}", api_key, payload=payload)
        after = api_request("GET", f"/entities/Souvenir/{record_id}", api_key)
        if not isinstance(after, dict):
            raise RuntimeError(f"Resposta inesperada ao verificar {record_id}.")
        verify_preserved_record(
            before,
            after,
            {"frente": target_url, "tras": back_url},
            "souvenir",
            payload,
        )
        updated += 1
        elapsed = time.monotonic() - started
        average = elapsed / index
        eta = average * (total - index)
        print(
            f"✓ [{index}/{total} | {index / total * 100:.0f}% | "
            f"decorrido {elapsed:.0f}s | ETA {eta:.0f}s] {before.get('name') or record_id}"
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
        rows = load_manifest(args.manifest.resolve(), args.location_id)
        prepared = preflight(api_key, rows)
        pending = sum(
            record.get("image_front") != desired_values(entry)[0]
            or record.get("display_orientation") != desired_values(entry)[1]
            for record, entry in prepared
        )
        print(f"Pré-verificação concluída: {len(prepared)} registos; {pending} pendentes.")
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
