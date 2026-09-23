#!/usr/bin/env python3
"""Promove recortes manuais de Souvenirs para a árvore canónica do país."""

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
from tools.souvenir_formats import crop_size  # noqa: E402


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


def photo_status_key(entry: dict[str, object]) -> str:
    source_hash = sha256(str(entry.get("source_url") or "").encode()).hexdigest()[:12]
    return f"{entry['location_id']}:machine-{entry['machine']}:{source_hash}"


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


def load_entries(
    staging: Path,
    location_id: str,
    record_ids: set[str] | None = None,
) -> tuple[dict[str, dict[str, object]], dict[int, list[dict[str, object]]]]:
    manifest = read_json(staging / "manifest.json")
    statuses = read_json(staging / "photo-status.json")
    selected: dict[str, dict[str, object]] = {}
    groups: dict[int, list[dict[str, object]]] = defaultdict(list)
    filenames: dict[str, str] = {}

    for record_id, raw_entry in manifest.items():
        if (
            not isinstance(raw_entry, dict)
            or str(raw_entry.get("location_id")) != location_id
            or (record_ids is not None and str(record_id) not in record_ids)
        ):
            continue
        entry = dict(raw_entry)
        required = ("slug", "name", "machine", "position", "source_url", "reference_url", "file", "orientation")
        missing = [field for field in required if entry.get(field) in (None, "")]
        if missing:
            raise ValueError(f"{record_id}: campos em falta: {', '.join(missing)}")
        source = Path(str(entry["file"]))
        if not source.is_file():
            raise ValueError(f"{record_id}: recorte em falta: {source}")
        expected_size = crop_size(entry.get("type") or "pressed", entry["orientation"])
        with Image.open(source) as image:
            if image.size != expected_size:
                raise ValueError(f"{record_id}: tamanho {image.size}; esperado {expected_size}")
            image.verify()
        existing_id = filenames.get(source.name)
        if existing_id and existing_id != record_id:
            raise ValueError(f"Nome repetido entre {existing_id} e {record_id}: {source.name}")
        filenames[source.name] = record_id
        entry["record_id"] = record_id
        entry["source_file"] = str(source)
        selected[record_id] = entry
        groups[int(entry["machine"])].append(entry)

    if not selected:
        raise ValueError(f"Não existem recortes concluídos para a location {location_id}.")
    if record_ids is not None:
        missing_ids = sorted(record_ids - set(selected))
        if missing_ids:
            raise ValueError(f"IDs concluídos em falta no manifesto: {', '.join(missing_ids)}")

    for machine, entries in groups.items():
        sources = {str(entry["source_url"]) for entry in entries}
        if len(sources) != 1:
            raise ValueError(f"Máquina {machine}: foram encontrados {len(sources)} links externos.")
        status = statuses.get(photo_status_key(entries[0]))
        if not isinstance(status, dict) or not status.get("completed"):
            raise ValueError(f"Máquina {machine}: fotografia ainda não confirmada como completa.")
        entries.sort(key=lambda entry: int(entry["position"]))

    return selected, dict(sorted(groups.items()))


def promote(args: argparse.Namespace) -> int:
    staging = args.staging.resolve()
    country_dir = args.country_dir.resolve()
    entries, groups = load_entries(staging, args.location_id, set(args.record_ids) if args.record_ids else None)
    front_dir = country_dir / "frente"
    original_dir = country_dir / "original"

    for entry in entries.values():
        source = Path(str(entry["source_file"]))
        destination = front_dir / source.name
        if (
            destination.exists()
            and file_digest(destination) != file_digest(source)
            and not args.replace_existing
        ):
            raise ValueError(
                f"Colisão com conteúdo diferente: {destination}. "
                "Usa --replace-existing apenas para substituir uma imagem automática pelo recorte confirmado."
            )

    print(f"Location {args.location_id}: {len(entries)} recortes em {len(groups)} fotografias.")
    print("Todas as fotografias estão confirmadas e os recortes têm dimensões válidas.")
    if not args.apply:
        print("Verificação concluída. Usa --apply para promover os ficheiros.")
        return 0

    downloads: dict[int, tuple[bytes, str, str]] = {}
    for machine, machine_entries in groups.items():
        entry = machine_entries[0]
        source_url = str(entry["source_url"])
        data = direct_download(source_url, str(entry["reference_url"]))
        extension = source_extension(data, source_url)
        filename = f"location-{args.location_id}-machine-{machine}{extension}"
        destination = original_dir / filename
        if destination.exists() and sha256(destination.read_bytes()).digest() != sha256(data).digest():
            raise ValueError(f"Colisão com conteúdo diferente: {destination}")
        downloads[machine] = (data, filename, source_url)

    country_relative = country_dir.relative_to(ROOT).as_posix()
    internal_links = parse_links(country_dir / "links-internos.txt")
    external_links = parse_links(country_dir / "links-externos.txt")
    canonical_manifest_path = country_dir / "recortes-manifest.json"
    canonical_manifest = read_json(canonical_manifest_path) if canonical_manifest_path.is_file() else {}

    front_dir.mkdir(parents=True, exist_ok=True)
    original_dir.mkdir(parents=True, exist_ok=True)
    for machine, (data, filename, _) in downloads.items():
        destination = original_dir / filename
        if not destination.exists():
            destination.write_bytes(data)

    for record_id, entry in entries.items():
        source = Path(str(entry.pop("source_file")))
        entry.pop("file", None)
        destination = front_dir / source.name
        if args.replace_existing or not destination.exists():
            shutil.copy2(source, destination)
        internal_url = f"{args.raw_base_url.rstrip('/')}/{country_relative}/frente/{destination.name}"
        source_url = str(entry["source_url"])
        slug = str(entry["slug"])
        internal_links.setdefault(slug, {})["frente"] = internal_url
        external_links.setdefault(slug, {})["frente"] = source_url
        original_filename = downloads[int(entry["machine"])][1]
        canonical_manifest[record_id] = {
            **entry,
            "front_file": f"frente/{destination.name}",
            "original_file": f"original/{original_filename}",
            "internal_front": internal_url,
            "external_front": source_url,
        }

    atomic_write(country_dir / "links-internos.txt", render_links(internal_links))
    atomic_write(country_dir / "links-externos.txt", render_links(external_links))
    atomic_write(
        canonical_manifest_path,
        json.dumps(canonical_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(f"Promovidos: {len(entries)} recortes, {len(downloads)} originais.")
    print(f"Destino: {country_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--country-dir", type=Path, default=DEFAULT_COUNTRY_DIR)
    parser.add_argument("--location-id", default="1851")
    parser.add_argument("--record-id", action="append", dest="record_ids", help="Limita a promoção a um ID concluído; pode repetir-se.")
    parser.add_argument("--raw-base-url", default=DEFAULT_RAW_BASE_URL)
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Substitui uma imagem existente pelo recorte explicitamente selecionado.",
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
