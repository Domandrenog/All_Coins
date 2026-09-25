#!/usr/bin/env python3
"""Promove lados recortados de Souvenirs para a árvore canónica do país."""

from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
from urllib.parse import urlparse

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = ROOT / "recortes_souvenir_teste"
DEFAULT_COUNTRY_DIR = ROOT / "fotos" / "paises" / "America" / "EUA" / "souvenir"
DEFAULT_RAW_BASE_URL = "https://raw.githubusercontent.com/Domandrenog/All_Coins/main"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sync_catalog_images_api import direct_download  # noqa: E402
from tools.souvenir_formats import (  # noqa: E402
    SIDE_FOLDERS,
    SIDE_LINK_FIELDS,
    SUPPORTED_SIDES,
    crop_size,
    display_orientation_for_crop,
    normalize_crop_format,
)


def read_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Ficheiro em falta: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Esperava um objeto JSON em {path}")
    return data


def normalized_task_id(key: object, entry: dict[str, object]) -> str:
    record_id = str(entry.get("record_id") or str(key).partition(":")[0])
    side = str(entry.get("side") or "front")
    if side not in SUPPORTED_SIDES:
        raise ValueError(f"{record_id}: lado inválido: {side}")
    return f"{record_id}:{side}"


def photo_status_key(entry: dict[str, object]) -> str:
    source_hash = sha256(str(entry.get("source_url") or "").encode()).hexdigest()[:12]
    return f"{entry['location_id']}:photo-{entry['machine']}:{source_hash}"


def photo_is_completed(statuses: dict[str, object], entry: dict[str, object]) -> bool:
    status = statuses.get(photo_status_key(entry))
    if isinstance(status, dict):
        return bool(status.get("completed"))
    source = str(entry.get("source_url") or "")
    side = str(entry.get("side") or "front")
    return any(
        isinstance(value, dict)
        and value.get("completed")
        and str(value.get("source_url") or "") == source
        and str(value.get("side") or "front") == side
        for value in statuses.values()
    )


def file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_links(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    result: dict[str, dict[str, str]] = {}
    current = ""
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.rstrip()
        if not line:
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current = line[:-1]
            if current in result:
                raise ValueError(f"Entrada duplicada em {path}:{number}: {current}")
            result[current] = {}
            continue
        if line.startswith("  ") and ":" in line and current:
            field, _, value = line.strip().partition(":")
            result[current][field] = value.lstrip()
            continue
        raise ValueError(f"Linha inesperada em {path}:{number}: {raw_line}")
    return result


def render_links(entries: dict[str, dict[str, str]]) -> str:
    blocks: list[str] = []
    for slug in sorted(entries, key=str.casefold):
        fields = entries[slug]
        lines = [f"{slug}:"]
        for field in ("frente", "tras"):
            if field in fields:
                value = fields[field]
                lines.append(f"  {field}:{f' {value}' if value else ''}")
        for field in sorted(set(fields) - {"frente", "tras"}):
            value = fields[field]
            lines.append(f"  {field}:{f' {value}' if value else ''}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def source_extension(data: bytes, source_url: str) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            image_format = str(image.format or "").upper()
    except Exception as exc:
        raise ValueError(f"A origem não devolveu uma imagem válida: {source_url}") from exc
    formats = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp"}
    if image_format in formats:
        return formats[image_format]
    suffix = Path(urlparse(source_url).path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"} else ".img"


def normalize_requested(values: set[str] | None) -> set[str] | None:
    if values is None:
        return None
    return {value if ":" in value else f"{value}:front" for value in values}


def load_entries(
    staging: Path,
    location_id: str,
    record_sides: set[str] | None = None,
) -> tuple[dict[str, dict[str, object]], dict[int, list[dict[str, object]]]]:
    manifest = read_json(staging / "manifest.json")
    statuses = read_json(staging / "photo-status.json")
    requested = normalize_requested(record_sides)
    selected: dict[str, dict[str, object]] = {}
    groups: dict[int, list[dict[str, object]]] = defaultdict(list)
    filenames: dict[str, str] = {}

    for key, raw_entry in manifest.items():
        if not isinstance(raw_entry, dict):
            continue
        entry = dict(raw_entry)
        task_id = normalized_task_id(key, entry)
        if (
            str(entry.get("location_id")) != location_id
            or (requested is not None and task_id not in requested)
        ):
            continue
        record_id, _, side = task_id.partition(":")
        entry["record_id"] = record_id
        entry["side"] = side
        entry["task_id"] = task_id
        entry.setdefault("type", "pressed")
        required = (
            "slug", "name", "type", "machine", "position", "source_url",
            "reference_url", "file",
        )
        missing = [field for field in required if entry.get(field) in (None, "")]
        if missing:
            raise ValueError(f"{task_id}: campos em falta: {', '.join(missing)}")
        crop_format = normalize_crop_format(
            entry.get("type"),
            entry.get("format") or entry.get("orientation"),
            entry.get("display_shape"),
        )
        entry["format"] = crop_format
        entry["orientation"] = display_orientation_for_crop(
            entry.get("type"), crop_format, entry.get("display_shape")
        )
        source = Path(str(entry["file"]))
        if not source.is_file():
            raise ValueError(f"{task_id}: recorte em falta: {source}")
        expected_size = crop_size(entry.get("type"), crop_format, entry.get("display_shape"))
        with Image.open(source) as image:
            if image.size != expected_size:
                raise ValueError(f"{task_id}: tamanho {image.size}; esperado {expected_size}")
            image.verify()
        existing_id = filenames.get(source.name)
        if existing_id and existing_id != task_id:
            raise ValueError(f"Nome repetido entre {existing_id} e {task_id}: {source.name}")
        filenames[source.name] = task_id
        if not photo_is_completed(statuses, entry):
            raise ValueError(f"Fotografia {entry['machine']}: ainda não confirmada como completa.")
        entry["source_file"] = str(source)
        selected[task_id] = entry
        groups[int(entry["machine"])].append(entry)

    if not selected:
        raise ValueError(f"Não existem lados concluídos para a location {location_id}.")
    if requested is not None:
        missing_ids = sorted(requested - set(selected))
        if missing_ids:
            raise ValueError(f"Lados pedidos em falta no manifesto: {', '.join(missing_ids)}")
    for entries in groups.values():
        entries.sort(key=lambda entry: (str(entry["side"]), int(entry["position"])))
    return selected, dict(sorted(groups.items()))


def destination_for_crop(
    country_dir: Path,
    canonical_entry: dict[str, object],
    entry: dict[str, object],
) -> Path:
    side = str(entry["side"])
    folder = country_dir / SIDE_FOLDERS[side]
    source = Path(str(entry["source_file"]))
    digest = file_digest(source)
    current_relative = str(canonical_entry.get(f"{side}_file") or "")
    current = country_dir / current_relative if current_relative else None
    if current is not None and current.is_file() and file_digest(current) == digest:
        return current
    preferred = folder / f"{entry['slug']}.jpg"
    if not preferred.exists() or file_digest(preferred) == digest:
        return preferred
    return folder / f"{entry['slug']}-{digest[:8]}.jpg"


def promote(args: argparse.Namespace) -> int:
    staging = args.staging.resolve()
    country_dir = args.country_dir.resolve()
    selections = set(args.record_sides or [])
    selections.update(f"{record_id}:front" for record_id in (args.record_ids or []))
    entries, groups = load_entries(
        staging, args.location_id, selections if selections else None
    )
    canonical_path = country_dir / "recortes-manifest.json"
    canonical_manifest = read_json(canonical_path) if canonical_path.is_file() else {}

    destinations: dict[str, Path] = {}
    for task_id, entry in entries.items():
        existing = canonical_manifest.get(str(entry["record_id"]))
        canonical_entry = existing if isinstance(existing, dict) else {}
        destinations[task_id] = destination_for_crop(country_dir, canonical_entry, entry)

    print(
        f"Location {args.location_id}: {len(entries)} lados de "
        f"{len({str(entry['record_id']) for entry in entries.values()})} Souvenirs "
        f"em {len(groups)} fotografias."
    )
    print("Todas as fotografias selecionadas estão confirmadas e os recortes têm dimensões válidas.")
    if not args.apply:
        for task_id, destination in destinations.items():
            print(f"- {task_id} -> {destination.relative_to(ROOT)}")
        print("Verificação concluída. Usa --apply para promover os ficheiros.")
        return 0

    downloads: dict[tuple[int, str, str], tuple[bytes, str]] = {}
    safe_location = args.location_id.replace("/", "-").replace("\\", "-")
    for entry in entries.values():
        key = (int(entry["machine"]), str(entry["side"]), str(entry["source_url"]))
        if key in downloads:
            continue
        data = direct_download(str(entry["source_url"]), str(entry["reference_url"]))
        extension = source_extension(data, str(entry["source_url"]))
        digest = sha256(data).hexdigest()[:8]
        base = f"location-{safe_location}-photo-{entry['machine']}-{entry['side']}"
        destination = country_dir / "original" / f"{base}{extension}"
        if destination.exists() and sha256(destination.read_bytes()).digest() != sha256(data).digest():
            destination = country_dir / "original" / f"{base}-{digest}{extension}"
        downloads[key] = (data, destination.name)

    internal_links = parse_links(country_dir / "links-internos.txt")
    external_links = parse_links(country_dir / "links-externos.txt")
    country_relative = country_dir.relative_to(ROOT).as_posix()
    (country_dir / "original").mkdir(parents=True, exist_ok=True)
    for data, filename in downloads.values():
        destination = country_dir / "original" / filename
        if not destination.exists():
            destination.write_bytes(data)

    for task_id, entry in entries.items():
        source = Path(str(entry["source_file"]))
        destination = destinations[task_id]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or file_digest(destination) != file_digest(source):
            shutil.copy2(source, destination)
        side = str(entry["side"])
        record_id = str(entry["record_id"])
        link_field = SIDE_LINK_FIELDS[side]
        internal_url = (
            f"{args.raw_base_url.rstrip('/')}/{country_relative}/"
            f"{SIDE_FOLDERS[side]}/{destination.name}"
        )
        source_url = str(entry["source_url"])
        slug = str(entry["slug"])
        internal_links.setdefault(slug, {})[link_field] = internal_url

        raw_existing = canonical_manifest.get(record_id)
        canonical = dict(raw_existing) if isinstance(raw_existing, dict) else {}
        previous_external = str(canonical.get(f"external_{side}") or "")
        if not source_url.startswith(args.raw_base_url.rstrip("/") + "/"):
            previous_external = source_url
            external_links.setdefault(slug, {})[link_field] = source_url
        elif previous_external:
            external_links.setdefault(slug, {})[link_field] = previous_external

        download_key = (int(entry["machine"]), side, source_url)
        original_filename = downloads[download_key][1]
        common_keys = (
            "name", "type", "previous_type", "type_was_overridden",
            "display_shape", "slug", "continent", "country", "city",
            "location_id", "location_name", "reference_url",
        )
        for field in common_keys:
            if field in entry:
                canonical[field] = entry[field]
        canonical.update({
            f"{side}_file": f"{SIDE_FOLDERS[side]}/{destination.name}",
            f"internal_{side}": internal_url,
            f"external_{side}": previous_external,
            f"previous_{side}": source_url,
            f"{side}_source_side": str(entry.get("source_side") or side),
            f"{side}_source_was_empty": bool(entry.get("source_was_empty")),
            f"original_{side}": f"original/{original_filename}",
            f"{side}_format": entry["format"],
            f"{side}_orientation": entry["orientation"],
            f"{side}_crop": entry.get("crop"),
            f"{side}_padding": entry.get("padding"),
            f"{side}_cleaned": entry.get("cleaned"),
            f"{side}_centered": entry.get("centered"),
        })
        if side == "front":
            canonical.update({
                "source_url": source_url,
                "front_file": f"frente/{destination.name}",
                "internal_front": internal_url,
                "external_front": previous_external,
                "original_file": f"original/{original_filename}",
                "orientation": entry["orientation"],
                "format": entry["format"],
                "machine": entry["machine"],
                "position": entry["position"],
                "crop": entry.get("crop"),
                "padding": entry.get("padding"),
                "cleaned": entry.get("cleaned"),
                "centered": entry.get("centered"),
            })
        elif "orientation" not in canonical:
            canonical["orientation"] = entry["orientation"]
        canonical_manifest[record_id] = canonical

    atomic_write(country_dir / "links-internos.txt", render_links(internal_links))
    atomic_write(country_dir / "links-externos.txt", render_links(external_links))
    atomic_write(
        canonical_path,
        json.dumps(canonical_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(f"Promovidos: {len(entries)} lados, {len(downloads)} originais.")
    print(f"Destino: {country_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--country-dir", type=Path, default=DEFAULT_COUNTRY_DIR)
    parser.add_argument("--location-id", default="1851")
    parser.add_argument(
        "--record-side", action="append", dest="record_sides",
        help="Limita a promoção a ID:front ou ID:back; pode repetir-se.",
    )
    parser.add_argument(
        "--record-id", action="append", dest="record_ids",
        help="Compatibilidade: seleciona a frente do ID indicado.",
    )
    parser.add_argument("--raw-base-url", default=DEFAULT_RAW_BASE_URL)
    parser.add_argument(
        "--replace-existing", action="store_true",
        help="Mantido por compatibilidade; substituições usam URL com hash quando necessário.",
    )
    parser.add_argument("--apply", action="store_true", help="Copia os ficheiros e atualiza manifests/links.")
    return parser.parse_args()


def main() -> int:
    try:
        return promote(parse_args())
    except (OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
