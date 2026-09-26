#!/usr/bin/env python3
"""Atualiza na Base44 apenas os lados de Souvenirs promovidos e selecionados."""

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

from tools.souvenir_formats import (  # noqa: E402
    SIDE_FIELDS,
    SUPPORTED_SIDES,
    SUPPORTED_SOUVENIR_TYPES,
)
from scripts.sync_coin_images_api import (  # noqa: E402
    API_KEY_ENV,
    READ_ONLY_FIELDS,
    api_request,
    load_dotenv,
)


def normalize_selections(values: set[str] | None) -> set[str] | None:
    if values is None:
        return None
    return {value if ":" in value else f"{value}:front" for value in values}


def available_sides(entry: dict[str, object]) -> set[str]:
    return {
        side
        for side in SUPPORTED_SIDES
        if str(entry.get(f"internal_{side}") or "").startswith(
            "https://raw.githubusercontent.com/"
        )
    }


def load_manifest(
    path: Path,
    location_id: str | None,
    record_sides: set[str] | None = None,
) -> list[tuple[str, dict[str, object]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Manifesto em falta: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Manifesto inválido: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError("O manifesto deve ser um objeto indexado pelo ID da Base44.")
    requested = normalize_selections(record_sides)
    grouped_requested: dict[str, set[str]] = {}
    if requested is not None:
        for selection in requested:
            record_id, separator, side = selection.partition(":")
            if not separator or side not in SUPPORTED_SIDES:
                raise ValueError(f"Seleção inválida: {selection}")
            grouped_requested.setdefault(record_id, set()).add(side)

    rows: list[tuple[str, dict[str, object]]] = []
    found: set[str] = set()
    for raw_record_id, raw_entry in data.items():
        record_id = str(raw_record_id)
        if not isinstance(raw_entry, dict):
            continue
        if location_id is not None and str(raw_entry.get("location_id")) != location_id:
            continue
        if requested is not None and record_id not in grouped_requested:
            continue
        entry = dict(raw_entry)
        sides = grouped_requested.get(record_id) if requested is not None else available_sides(entry)
        sides = set(sides or set())
        if not sides:
            continue
        entry["_selected_sides"] = sorted(sides)
        rows.append((record_id, entry))
        found.update(f"{record_id}:{side}" for side in sides)
    rows.sort(
        key=lambda item: (
            str(item[1].get("city") or "").casefold(),
            str(item[1].get("location_name") or "").casefold(),
            str(item[1].get("name") or "").casefold(),
            item[0],
        )
    )
    if not rows:
        raise ValueError("O manifesto não contém lados no âmbito pedido.")
    if requested is not None:
        missing = sorted(requested - found)
        if missing:
            raise ValueError(f"Lados pedidos em falta no manifesto: {', '.join(missing)}")
    return rows


def selected_sides(entry: dict[str, object]) -> list[str]:
    values = entry.get("_selected_sides")
    if isinstance(values, list):
        sides = [str(value) for value in values]
    else:
        sides = ["front"]
    if any(side not in SUPPORTED_SIDES for side in sides):
        raise ValueError(f"Lados inválidos no manifesto: {sides}")
    return sides


def desired_side(entry: dict[str, object], side: str) -> str:
    url = str(entry.get(f"internal_{side}") or "")
    if not url.startswith("https://raw.githubusercontent.com/"):
        raise ValueError(f"URL interno inválido para {side}: {url}")
    return url


def desired_orientation(entry: dict[str, object]) -> str:
    orientation = str(
        entry.get("front_orientation")
        or entry.get("orientation")
        or "auto"
    )
    if orientation not in {"auto", "portrait", "landscape"}:
        raise ValueError(f"Orientação inválida: {orientation}")
    return orientation


def desired_has_back_image(entry: dict[str, object]) -> bool | None:
    if not entry.get("has_back_image_was_overridden"):
        return None
    value = entry.get("has_back_image_override")
    if not isinstance(value, bool):
        raise ValueError("Override de imagem de verso inválido no manifesto.")
    return value


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
        back_image_override = desired_has_back_image(entry)
        if back_image_override is not None and expected_type != "coin":
            raise ValueError(
                f"{record_id}: override de verso só é válido para moedas."
            )
        if back_image_override is False and "back" in selected_sides(entry):
            raise ValueError(
                f"{record_id}: o manifesto não pode enviar o Verso e desativá-lo."
            )
        current_type = str(record.get("type") or "")
        previous_type = str(entry.get("previous_type") or "")
        type_was_overridden = bool(entry.get("type_was_overridden"))
        if current_type != expected_type and not (
            type_was_overridden and current_type == previous_type
        ):
            raise ValueError(
                f"{record_id}: tipo mudou desde o recorte; "
                f"esperado={expected_type!r}, atual={current_type!r}."
            )
        for side in selected_sides(entry):
            target_url = desired_side(entry, side)
            accepted = {
                str(entry.get(f"external_{side}") or ""),
                str(entry.get(f"previous_{side}") or ""),
                str(entry.get("source_url") or "") if side == "front" else "",
                target_url,
            }
            accepted.discard("")
            if entry.get(f"{side}_source_was_empty"):
                accepted.add("")
            field = SIDE_FIELDS[side]
            current_url = str(record.get(field) or "")
            if current_url not in accepted:
                raise ValueError(
                    f"{record_id}: {field} mudou desde o recorte; atual={current_url!r}."
                )
        prepared.append((record, entry))
    return prepared


def difference_payload(
    record: dict[str, object],
    entry: dict[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {}
    sides = selected_sides(entry)
    expected_type = str(entry.get("type") or "pressed")
    if entry.get("type_was_overridden") and record.get("type") != expected_type:
        payload["type"] = expected_type
    for side in sides:
        field = SIDE_FIELDS[side]
        target = desired_side(entry, side)
        if record.get(field) != target:
            payload[field] = target
    back_image_override = desired_has_back_image(entry)
    if back_image_override is not None:
        if record.get("has_back_image") != back_image_override:
            payload["has_back_image"] = back_image_override
    elif "back" in sides and record.get("has_back_image") is not True:
        payload["has_back_image"] = True
    if "front" in sides:
        orientation = desired_orientation(entry)
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
        if not isinstance(current, dict):
            raise RuntimeError(f"Resposta inesperada na validação final de {record_id}.")
        for side in selected_sides(entry):
            field = SIDE_FIELDS[side]
            if current.get(field) != desired_side(entry, side):
                raise RuntimeError(f"{record_id}: URL final incorreto em {field}.")
        expected_type = str(entry.get("type") or "pressed")
        if current.get("type") != expected_type:
            raise RuntimeError(f"{record_id}: tipo final incorreto.")
        back_image_override = desired_has_back_image(entry)
        if back_image_override is not None:
            if current.get("has_back_image") != back_image_override:
                raise RuntimeError(
                    f"{record_id}: estado da imagem de verso não ficou correto."
                )
        elif "back" in selected_sides(entry):
            if current.get("has_back_image") is not True:
                raise RuntimeError(f"{record_id}: imagem de verso não ficou ativada.")
        if "front" in selected_sides(entry):
            if current.get("display_orientation") != desired_orientation(entry):
                raise RuntimeError(f"{record_id}: orientação final incorreta.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--location-id")
    parser.add_argument(
        "--record-side", action="append", dest="record_sides",
        help="Limita a atualização a ID:front ou ID:back; pode repetir-se.",
    )
    parser.add_argument(
        "--record-id", action="append", dest="record_ids",
        help="Compatibilidade: seleciona a frente do ID indicado.",
    )
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
    selections = set(args.record_sides or [])
    selections.update(f"{record_id}:front" for record_id in (args.record_ids or []))
    try:
        rows = load_manifest(
            args.manifest.resolve(),
            args.location_id,
            selections if selections else None,
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
