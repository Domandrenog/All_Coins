#!/usr/bin/env python3
"""Migra imagens de collection e notes para a estrutura canónica do repositório."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import sys
import time
from collections import Counter, deque
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image, ImageOps

try:
    from .sync_coin_images_api import (
        API_KEY_ENV,
        DEFAULT_RAW_BASE_URL,
        EXTERNAL_LINKS_FILENAME,
        INTERNAL_LINKS_FILENAME,
        PHOTOS_ROOT,
        READ_ONLY_FIELDS,
        api_request,
        continent_folder,
        country_file_slug,
        country_folder,
        format_duration,
        git_commit_and_push,
        load_dotenv,
        slugify,
        write_country_links,
    )
except ImportError:
    from sync_coin_images_api import (
        API_KEY_ENV,
        DEFAULT_RAW_BASE_URL,
        EXTERNAL_LINKS_FILENAME,
        INTERNAL_LINKS_FILENAME,
        PHOTOS_ROOT,
        READ_ONLY_FIELDS,
        api_request,
        continent_folder,
        country_file_slug,
        country_folder,
        format_duration,
        git_commit_and_push,
        load_dotenv,
        slugify,
        write_country_links,
    )


CATALOGS = {
    "collection": {
        "entity": "SpecialCoin",
        "year_field": "year",
        "extra_slug_field": "commemorative_name",
        "label": "moeda de coleção",
    },
    "notes": {
        "entity": "CountryNote",
        "year_field": "year",
        "extra_slug_field": "",
        "label": "nota",
    },
}

DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_RETRY_SECONDS = 5


def catalog_slugify(value: str) -> str:
    """Preserva letras que o NFKD não translitera, como Đ/đ em Đồng."""
    return slugify(value.replace("Đ", "D").replace("đ", "d"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migra imagens de collection ou notes.")
    parser.add_argument("--catalog", choices=sorted(CATALOGS), required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--country", help="Filtro exato por país na API.")
    scope.add_argument("--record-id", help="ID exato do registo.")
    scope.add_argument("--all", action="store_true", help="Processa todos os registos da categoria.")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--api-key-env", default=API_KEY_ENV)
    parser.add_argument("--raw-base-url", default=DEFAULT_RAW_BASE_URL)
    parser.add_argument("--download-current", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--overwrite-images", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-git-push", action="store_true")
    parser.add_argument("--git-commit-message", default="Update catalogue image assets")
    parser.add_argument(
        "--cdp-url",
        default="http://127.0.0.1:9222",
        help="Sessão Chrome existente usada quando a origem bloqueia downloads diretos.",
    )
    parser.add_argument("--no-cdp-fallback", action="store_true")
    parser.add_argument(
        "--keep-portrait",
        action="store_true",
        help="Não roda imagens verticais. Por defeito, as notas verticais são rodadas para horizontal.",
    )
    return parser.parse_args()


def catalogue_path(record: dict[str, object], catalog: str) -> Path:
    return (
        PHOTOS_ROOT
        / continent_folder(str(record.get("continent") or ""))
        / country_folder(str(record.get("country") or ""), None)
        / catalog
    )


def record_label(record: dict[str, object], catalog: str) -> str:
    year_field = str(CATALOGS[catalog]["year_field"])
    name = str(record.get("name") or "Sem nome").strip()
    year = str(record.get(year_field) or "").strip()
    return f"{name} ({year})" if year else name


def base_record_slug(record: dict[str, object], catalog: str) -> str:
    config = CATALOGS[catalog]
    fields = [
        country_file_slug(str(record.get("country") or "")),
        catalog_slugify(str(record.get("name") or "")),
    ]
    extra_field = str(config["extra_slug_field"])
    if extra_field:
        fields.append(catalog_slugify(str(record.get(extra_field) or "")))
    fields.append(catalog_slugify(str(record.get(str(config["year_field"])) or "")))
    slug = "-".join(field for field in fields if field)
    if not slug:
        raise RuntimeError(f"Não foi possível gerar slug para {record!r}")
    return slug


def unique_record_slugs(records: list[dict[str, object]], catalog: str) -> dict[str, str]:
    bases = [base_record_slug(record, catalog) for record in records]
    counts = Counter(bases)
    result: dict[str, str] = {}
    used: set[str] = set()
    for index, (record, base) in enumerate(zip(records, bases)):
        record_id = str(record.get("id") or index)
        slug = f"{base}-{record_id[-8:]}" if counts[base] > 1 else base
        if slug in used:
            slug = f"{slug}-{index + 1}"
        used.add(slug)
        result[record_id] = slug
    return result


def generated_links(
    record: dict[str, object], catalog: str, slug: str, raw_base_url: str
) -> dict[str, str]:
    folder = catalogue_path(record, catalog).as_posix()
    base = raw_base_url.rstrip("/")
    return {
        "frente": f"{base}/{folder}/frente/{slug}.jpg",
        "tras": f"{base}/{folder}/tras/{slug}.jpg",
    }


def list_records(api_key: str, args: argparse.Namespace) -> list[dict[str, object]]:
    entity = str(CATALOGS[args.catalog]["entity"])
    if args.record_id:
        data = api_request("GET", f"/entities/{entity}/{args.record_id}", api_key)
        if not isinstance(data, dict):
            raise RuntimeError(f"Resposta inesperada para {args.record_id}: {data!r}")
        return [data]
    query: dict[str, object] = {"limit": args.limit}
    if args.country:
        query["q"] = json.dumps({"country": args.country}, ensure_ascii=False)
    data = api_request("GET", f"/entities/{entity}", api_key, query=query)
    if not isinstance(data, list):
        raise RuntimeError(f"Resposta inesperada ao listar {entity}: {data!r}")
    return [row for row in data if isinstance(row, dict)]


def normalize_image(data: bytes, destination: Path, rotate_portrait: bool) -> bool:
    """Guarda JPEG com EXIF aplicado e roda digitalizações verticais para horizontal."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source)
        rotated = rotate_portrait and image.height > image.width
        if rotated:
            image = image.transpose(Image.Transpose.ROTATE_270)
        if image.mode in {"RGBA", "LA"}:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        image.save(destination, format="JPEG", quality=95, optimize=True)
    return rotated


class CdpImageDownloader:
    def __init__(self, cdp_url: str) -> None:
        self.cdp_url = cdp_url
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.numista_prepared = False

    def start(self) -> None:
        if self.browser is not None and self.browser.is_connected():
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright não está instalado.") from exc
        self.playwright = sync_playwright().start()
        try:
            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
        except Exception as exc:
            self.playwright.stop()
            self.playwright = None
            raise RuntimeError(
                f"Não foi possível ligar ao Chrome em {self.cdp_url}. "
                "Abre uma sessão com remote-debugging-port=9222 e resolve o Cloudflare."
            ) from exc
        if not self.browser.contexts:
            raise RuntimeError("A sessão Chrome não tem um contexto disponível.")
        self.context = self.browser.contexts[0]
        for existing_page in self.context.pages:
            if (
                "numista.com" in existing_page.url
                and "challenge.php" not in existing_page.url
                and "checking connection" not in existing_page.title().lower()
            ):
                self.numista_prepared = True
                break
        # Mantém intacto o separador em que o utilizador resolveu o desafio.
        self.page = self.context.new_page()

    def download(self, url: str, referer_url: str = "") -> bytes:
        self.start()
        assert self.page is not None
        if referer_url and "numista.com" in url.lower() and not self.numista_prepared:
            response = self.page.goto(referer_url, wait_until="domcontentloaded", timeout=60_000)
            if response is not None and response.status >= 400:
                raise RuntimeError(f"Numista devolveu HTTP {response.status} em {referer_url}")
            for _ in range(20):
                if "challenge.php" not in self.page.url and "checking connection" not in self.page.title().lower():
                    break
                self.page.wait_for_timeout(1_000)
            if "challenge.php" in self.page.url or "checking connection" in self.page.title().lower():
                raise RuntimeError("O desafio Cloudflare do Numista ainda não foi resolvido na janela Chrome.")
            self.numista_prepared = True
        response = self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        if response is not None and "image" not in response.headers.get("content-type", "").lower():
            # A proteção pode apresentar uma verificação curta também no host
            # das imagens. Espera pela conclusão e repete o URL original.
            for _ in range(20):
                if "challenge" not in self.page.url and "checking connection" not in self.page.title().lower():
                    break
                self.page.wait_for_timeout(1_000)
            response = self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        if response is None:
            raise RuntimeError("O browser não recebeu resposta da imagem.")
        content_type = response.headers.get("content-type", "")
        if response.status != 200 or "image" not in content_type.lower():
            raise RuntimeError(f"Resposta inválida no browser: HTTP {response.status}, {content_type}")
        return response.body()

    def close(self) -> None:
        # Desliga apenas o cliente Playwright; não fecha a sessão Chrome do utilizador.
        if self.page is not None:
            try:
                self.page.close()
            except Exception:  # noqa: BLE001
                pass
        self.page = None
        self.context = None
        self.browser = None
        if self.playwright is not None:
            self.playwright.stop()
            self.playwright = None


def direct_download(url: str, referer_url: str = "") -> bytes:
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "image/*,*/*;q=0.8"}
    if referer_url:
        headers["Referer"] = referer_url
    request = Request(url, headers=headers)
    with urlopen(request, timeout=60) as response:
        content_type = response.headers.get("Content-Type", "")
        if "image" not in content_type.lower():
            raise RuntimeError(f"A origem não devolveu uma imagem ({content_type or 'sem content-type'}).")
        return response.read()


def download_and_normalize(
    url: str,
    destination: Path,
    referer_url: str,
    overwrite: bool,
    rotate_portrait: bool,
    cdp_downloader: CdpImageDownloader | None,
) -> tuple[str, bool]:
    if destination.exists() and not overwrite:
        return "exists", False

    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            data = direct_download(url, referer_url)
            return "downloaded", normalize_image(data, destination, rotate_portrait)
        except (HTTPError, URLError, RuntimeError) as exc:
            last_error = exc
            if attempt < DOWNLOAD_ATTEMPTS and not isinstance(exc, HTTPError):
                time.sleep(DOWNLOAD_RETRY_SECONDS)
                continue
            break

    if cdp_downloader is not None:
        data = cdp_downloader.download(url, referer_url)
        return "downloaded-browser", normalize_image(data, destination, rotate_portrait)
    raise RuntimeError(f"Falha ao descarregar {url}: {last_error}")


def mutable_payload(
    record: dict[str, object], front_url: str, back_url: str
) -> dict[str, object]:
    payload = {key: value for key, value in record.items() if key not in READ_ONLY_FIELDS}
    payload["image_frente"] = front_url
    payload["image_verso"] = back_url
    return payload


def verify_preserved_record(
    before: dict[str, object], after: dict[str, object], target: dict[str, str]
) -> None:
    if after.get("image_frente") != target["frente"] or after.get("image_verso") != target["tras"]:
        raise RuntimeError("A API não guardou os dois URLs esperados.")
    excluded = READ_ONLY_FIELDS | {"image_frente", "image_verso"}
    for key, value in before.items():
        if key not in excluded and after.get(key) != value:
            raise RuntimeError(f"Campo alterado inesperadamente durante a verificação: {key}")


def main() -> int:
    args = parse_args()
    load_dotenv()
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Define {args.api_key_env} no ficheiro .env.", file=sys.stderr)
        return 2
    if args.api_only and (args.download_current or args.download_only):
        print("--api-only é incompatível com opções de download.", file=sys.stderr)
        return 2

    records = list_records(api_key, args)
    if not records:
        print("Nenhum registo encontrado.", file=sys.stderr)
        return 2

    slugs = unique_record_slugs(records, args.catalog)
    pending: list[tuple[dict[str, object], dict[str, str], dict[str, object]]] = []
    changed_folders: set[Path] = set()
    browser = None if args.no_cdp_fallback else CdpImageDownloader(args.cdp_url)
    if browser is not None:
        atexit.register(browser.close)
    started = time.monotonic()
    durations: deque[float] = deque(maxlen=10)
    previous_started: float | None = None
    print(f"Registos encontrados: {len(records)} ({args.catalog})")

    for index, record in enumerate(records, start=1):
        now = time.monotonic()
        if previous_started is not None:
            durations.append(now - previous_started)
        previous_started = now
        completed = index - 1
        eta = "a calcular"
        if len(durations) >= 3:
            seconds = sum(durations) / len(durations) * (len(records) - completed)
            eta = f"~{format_duration(seconds)}"
        print(
            f"\n[{completed}/{len(records)} ({completed / len(records) * 100:.0f}%) | "
            f"decorrido: {format_duration(now - started)} | ETA: {eta}]"
        )
        print(f"{CATALOGS[args.catalog]['label'].capitalize()}: {record_label(record, args.catalog)}")

        record_id = str(record.get("id") or "")
        if not record_id:
            raise RuntimeError(f"Registo sem id: {record!r}")
        slug = slugs[record_id]
        folder = catalogue_path(record, args.catalog)
        target = generated_links(record, args.catalog, slug, args.raw_base_url)
        source = {
            "frente": str(record.get("image_frente") or ""),
            "tras": str(record.get("image_verso") or ""),
        }
        target_files = {
            "frente": folder / "frente" / f"{slug}.jpg",
            "tras": folder / "tras" / f"{slug}.jpg",
        }

        if source == target and all(path.exists() for path in target_files.values()):
            print("Já migrado; sem alterações.")
            continue
        if not source["frente"] or not source["tras"]:
            print("Saltado: falta pelo menos uma imagem de origem.")
            continue

        if args.download_current or args.download_only:
            referer = str(record.get("url_numista") or record.get("url_ucoin") or "")
            for side in ("frente", "tras"):
                if not (args.apply or args.download_only):
                    print(f"Download {side}: dry-run -> {target_files[side]}")
                    continue
                status, rotated = download_and_normalize(
                    source[side],
                    target_files[side],
                    referer,
                    args.overwrite_images,
                    args.catalog == "notes" and not args.keep_portrait,
                    browser,
                )
                rotation = " | rodada para horizontal" if rotated else ""
                print(f"Download {side}: {status}{rotation} -> {target_files[side]}")

        if args.apply and not args.download_current and not args.download_only:
            missing = [side for side, path in target_files.items() if not path.exists()]
            if missing:
                print(f"Saltado: imagens locais em falta ({', '.join(missing)}).")
                continue

        if (args.apply or args.download_only) and not args.api_only:
            write_country_links(folder, slug, source, EXTERNAL_LINKS_FILENAME)
            write_country_links(folder, slug, target, INTERNAL_LINKS_FILENAME)
            changed_folders.add(folder)

        if args.download_only or not args.apply:
            continue
        pending.append((record, target, mutable_payload(record, target["frente"], target["tras"])))

    if browser is not None:
        browser.close()

    if (args.apply or args.download_only) and changed_folders and not args.no_git_push:
        git_commit_and_push(args.git_commit_message)

    entity = str(CATALOGS[args.catalog]["entity"])
    for index, (before, target, payload) in enumerate(pending, start=1):
        record_id = str(before["id"])
        api_request("PUT", f"/entities/{entity}/{record_id}", api_key, payload=payload)
        verified = api_request("GET", f"/entities/{entity}/{record_id}", api_key)
        if not isinstance(verified, dict):
            raise RuntimeError(f"Resposta inesperada ao verificar {record_id}: {verified!r}")
        verify_preserved_record(before, verified, target)
        print(f"✓ API atualizada e verificada [{index}/{len(pending)}] — {record_label(before, args.catalog)}")

    if args.download_only:
        print("\nDownload concluído; a API não foi alterada.")
    elif not args.apply:
        print("\nDry-run concluído; nenhuma alteração foi aplicada.")
    else:
        print(
            f"\nConcluído: {len(pending)} atualizações API | "
            f"tempo total: {format_duration(time.monotonic() - started)}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
