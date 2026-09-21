#!/usr/bin/env python3
"""Atualiza URLs de imagens de moedas na API para apontarem para o raw do GitHub."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from collections import deque
from io import BytesIO
from pathlib import Path
from shutil import which
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

API_BASE_URL = "https://track-coin-collection.base44.app/api"
API_KEY_ENV = "ALL_COINS_API_KEY"
DEFAULT_RAW_BASE_URL = "https://raw.githubusercontent.com/Domandrenog/All_Coins/main"
PHOTOS_ROOT = Path("fotos/paises")
NORMAL_TYPE_FOLDER = "normal"
INTERNAL_LINKS_FILENAME = "links-internos.txt"
EXTERNAL_LINKS_FILENAME = "links-externos.txt"
READ_ONLY_FIELDS = {"id", "created_date", "updated_date", "created_by_id"}
BROWSER_DOWNLOAD_ATTEMPTS = 3
BROWSER_RETRY_DELAY_SECONDS = 5
API_REQUEST_ATTEMPTS = 3
API_RETRY_DELAY_SECONDS = 5
API_RATE_LIMIT_ATTEMPTS = 5
API_RATE_LIMIT_RETRY_DELAY_SECONDS = 60
IMAGE_DOWNLOAD_ATTEMPTS = 3
IMAGE_DOWNLOAD_RETRY_DELAY_SECONDS = 5


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def format_duration(seconds: float) -> str:
    total_seconds = max(0, round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def coin_label(coin: dict[str, object]) -> str:
    """Return the concise coin name used in normal progress output."""
    name = str(coin.get("name") or "Moeda sem nome").strip()
    years = str(coin.get("years") or "").strip()
    return f"{name} ({years})" if years else name

COUNTRY_SLUG_ALIASES = {
    "bahamas": ["bahamas"],
    "polonia": ["polonia", "poland"],
    "poland": ["poland", "polonia"],
    "bielorrussia": ["bielorrussia", "belarus"],
    "belarus": ["belarus", "bielorrussia"],
    "brasil": ["brasil", "brazil"],
    "brazil": ["brazil", "brasil"],
    "china": ["china"],
    "coreia-do-sul": ["coreia-do-sul", "south-korea"],
    "south-korea": ["south-korea", "coreia-do-sul"],
    "emirados-arabes-unidos": ["emirados-arabes-unidos", "united-arab-emirates"],
    "united-arab-emirates": ["united-arab-emirates", "emirados-arabes-unidos"],
    "eua": ["eua", "united-states", "usa"],
    "united-states": ["united-states", "eua", "usa"],
    "usa": ["usa", "eua", "united-states"],
    "japao": ["japao", "japan"],
    "japan": ["japan", "japao"],
    "macau": ["macau"],
    "malasia": ["malasia", "malaysia"],
    "malaysia": ["malaysia", "malasia"],
    "mauricia": ["mauricia", "mauritius"],
    "mauricias": ["mauricias", "mauritius"],
    "mauritius": ["mauritius", "mauricia", "mauricias"],
    "seychelles": ["seychelles"],
    "romenia": ["romenia", "romania"],
    "romania": ["romania", "romenia"],
    "russia": ["russia"],
    "singapura": ["singapura", "singapore"],
    "singapore": ["singapore", "singapura"],
    "sri-lanka": ["sri-lanka"],
    "tailandia": ["tailandia", "thailand"],
    "thailand": ["thailand", "tailandia"],
    "hong-kong": ["hong-kong"],
    "taiwan": ["taiwan"],
    "tunisia": ["tunisia"],
}

COUNTRY_FILE_SLUGS = {
    "bahamas": "bahamas",
    "polonia": "poland",
    "poland": "poland",
    "bielorrussia": "belarus",
    "belarus": "belarus",
    "brasil": "brazil",
    "brazil": "brazil",
    "china": "china",
    "coreia-do-sul": "south-korea",
    "south-korea": "south-korea",
    "emirados-arabes-unidos": "united-arab-emirates",
    "united-arab-emirates": "united-arab-emirates",
    "eua": "united-states",
    "united-states": "united-states",
    "usa": "united-states",
    "japao": "japan",
    "japan": "japan",
    "macau": "macau",
    "malasia": "malaysia",
    "malaysia": "malaysia",
    "mauricia": "mauritius",
    "mauricias": "mauritius",
    "mauritius": "mauritius",
    "seychelles": "seychelles",
    "romenia": "romania",
    "romania": "romania",
    "russia": "russia",
    "singapura": "singapore",
    "singapore": "singapore",
    "sri-lanka": "sri-lanka",
    "tailandia": "thailand",
    "thailand": "thailand",
    "hong-kong": "hong-kong",
    "taiwan": "taiwan",
    "tunisia": "tunisia",
}

COUNTRY_FOLDERS = {
    "bahamas": "Bahamas",
    "polonia": "Polonia",
    "poland": "Polonia",
    "bielorrussia": "Bielorrussia",
    "belarus": "Bielorrussia",
    "brasil": "Brasil",
    "brazil": "Brasil",
    "china": "China",
    "coreia-do-sul": "CoreiaDoSul",
    "south-korea": "CoreiaDoSul",
    "emirados-arabes-unidos": "EmiradosArabesUnidos",
    "united-arab-emirates": "EmiradosArabesUnidos",
    "eua": "EUA",
    "united-states": "EUA",
    "usa": "EUA",
    "japao": "Japao",
    "japan": "Japao",
    "macau": "Macau",
    "malasia": "Malasia",
    "malaysia": "Malasia",
    "mauricia": "Mauricias",
    "mauricias": "Mauricias",
    "mauritius": "Mauricias",
    "seychelles": "Seychelles",
    "romenia": "Romenia",
    "romania": "Romenia",
    "russia": "Russia",
    "singapura": "Singapura",
    "singapore": "Singapura",
    "sri-lanka": "SriLanka",
    "tailandia": "Tailandia",
    "thailand": "Tailandia",
    "hong-kong": "HongKong",
    "taiwan": "Taiwan",
    "tunisia": "Tunisia",
}

CONTINENT_FOLDERS = {
    "africa": "Africa",
    "america": "America",
    "asia": "Asia",
    "europa": "Europa",
    "oceania": "Oceania",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Busca moedas na API e atualiza image_frente/image_verso com URLs raw do GitHub."
    )
    parser.add_argument("--country", help="Filtro exato por país na API, ex.: Polonia.")
    parser.add_argument("--name", help="Filtro exato por nome na API, opcional.")
    parser.add_argument("--years", help="Filtro exato por anos na API, opcional.")
    parser.add_argument("--slug", help="Slug manual para uma moeda específica, ex.: poland-1-grosz-2018.")
    parser.add_argument("--coin-id", help="ID da moeda na API, se já souberes qual é.")
    parser.add_argument(
        "--country-folder",
        help="Nome da pasta do país, ex.: Polonia. O caminho completo inclui fotos/paises/<continente>/<país>/normal.",
    )
    parser.add_argument("--raw-base-url", default=DEFAULT_RAW_BASE_URL, help="Base raw do GitHub.")
    parser.add_argument("--limit", type=int, default=1000, help="Máximo de moedas a listar quando não há coin-id.")
    parser.add_argument("--api-key-env", default=API_KEY_ENV, help="Nome da variável de ambiente com a API key.")
    parser.add_argument("--download-current", action="store_true", help="Descarrega as imagens atuais da API antes de atualizar.")
    parser.add_argument("--download-only", action="store_true", help="Descarrega as imagens atuais, mas não atualiza a API.")
    parser.add_argument("--api-only", action="store_true", help="Atualiza só a API; não descarrega, não escreve links e não faz Git.")
    parser.add_argument("--overwrite-images", action="store_true", help="Substitui imagens locais existentes ao descarregar.")
    parser.add_argument("--include-without-ucoin", action="store_true", help="Inclui moedas que não tenham links i.ucoin.net nos dois lados.")
    parser.add_argument("--ucoin-browser-profile", default=".ucoin-profile", help="Perfil Chromium com sessão uCoin para fallback de download.")
    parser.add_argument("--no-ucoin-browser-fallback", action="store_true", help="Não usa Chromium/Playwright quando o download i.ucoin.net via curl falha.")
    parser.add_argument("--apply", action="store_true", help="Aplica a atualização na API. Sem isto, só mostra o plano.")
    parser.add_argument("--no-git-push", action="store_true", help="Não faz git add/commit/push automático em execuções reais.")
    parser.add_argument("--git-commit-message", default="Update coin image assets", help="Mensagem do commit automático.")
    return parser.parse_args()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def country_file_slug(country: str) -> str:
    country_slug = slugify(country)
    return COUNTRY_FILE_SLUGS.get(country_slug, country_slug)


def default_country_folder(country_slug: str) -> str:
    return "".join(part.capitalize() for part in country_slug.split("-") if part)


def country_folder(country: str, explicit_folder: str | None) -> str:
    if explicit_folder:
        return explicit_folder.strip("/")
    country_slug = slugify(country)
    return COUNTRY_FOLDERS.get(country_slug, default_country_folder(country_slug))


def continent_folder(continent: str) -> str:
    continent_slug = slugify(continent)
    if not continent_slug:
        raise RuntimeError("A moeda não tem continente definido na API.")
    return CONTINENT_FOLDERS.get(continent_slug, default_country_folder(continent_slug))


def normal_country_path(country: str, continent: str, explicit_country_folder: str | None = None) -> Path:
    return (
        PHOTOS_ROOT
        / continent_folder(continent)
        / country_folder(country, explicit_country_folder)
        / NORMAL_TYPE_FOLDER
    )


def coin_file_slug(coin: dict[str, object], manual_slug: str | None = None) -> str:
    if manual_slug:
        return manual_slug

    image_url = str(coin.get("image_frente") or coin.get("image_verso") or "")
    # Base44 file URLs usually start with an opaque upload id. For those files,
    # generate a stable catalogue slug from the coin metadata instead.
    if "base44.app/" not in image_url.lower():
        image_slug = image_file_slug(image_url)
        if image_slug:
            return image_slug

    country = str(coin.get("country") or "")
    name = str(coin.get("name") or "")
    years = str(coin.get("years") or "")

    parts = [country_file_slug(country), slugify(name)]
    if years:
        parts.append(slugify(years))

    slug = "-".join(part for part in parts if part)
    if not slug:
        raise RuntimeError(f"Não consegui gerar slug para moeda: {coin!r}")
    return slug


def duplicate_coin_slug(base_slug: str, coin: dict[str, object]) -> str:
    parts = [
        slugify(str(coin.get("name") or "")),
        slugify(str(coin.get("years") or "")),
        slugify(str(coin.get("notes") or "")),
    ]
    suffix = "-".join(part for part in parts if part)
    if suffix:
        return f"{base_slug}-{suffix}"

    coin_id = str(coin.get("id") or "")
    if coin_id:
        return f"{base_slug}-{coin_id[-8:]}"
    return base_slug


def unique_coin_slugs(coins: list[dict[str, object]], manual_slug: str | None = None) -> dict[str, str]:
    base_slugs = [coin_file_slug(coin, manual_slug) for coin in coins]
    duplicate_bases = {slug for slug in base_slugs if base_slugs.count(slug) > 1}
    used_slugs: set[str] = set()
    slugs: dict[str, str] = {}

    for index, (coin, base_slug) in enumerate(zip(coins, base_slugs)):
        coin_id = str(coin.get("id") or index)
        slug = duplicate_coin_slug(base_slug, coin) if base_slug in duplicate_bases else base_slug
        if slug in used_slugs:
            slug = f"{slug}-{coin_id[-8:]}"
        used_slugs.add(slug)
        slugs[coin_id] = slug

    return slugs


def image_file_slug(url: str) -> str:
    if not url:
        return ""

    filename = Path(unquote(urlparse(url).path)).name
    stem = Path(filename).stem
    return slugify(stem.replace("_", "-"))


def generated_image_links(coin: dict[str, object], args: argparse.Namespace, slug: str) -> dict[str, str]:
    folder = normal_country_path(
        str(coin.get("country") or args.country or ""),
        str(coin.get("continent") or ""),
        args.country_folder,
    ).as_posix()
    base_url = args.raw_base_url.rstrip("/")
    return {
        "frente": f"{base_url}/{folder}/frente/{slug}.jpg",
        "tras": f"{base_url}/{folder}/tras/{slug}.jpg",
    }


def api_request(method: str, path: str, api_key: str, payload: object | None = None, query: dict[str, object] | None = None) -> object:
    url = f"{API_BASE_URL}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"

    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = Request(
        url,
        data=body,
        method=method,
        headers={"api_key": api_key, "Content-Type": "application/json"},
    )

    max_attempts = API_RATE_LIMIT_ATTEMPTS
    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(request, timeout=30) as response:
                response_body = response.read().decode("utf-8")
                return json.loads(response_body) if response_body else {}
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < max_attempts:
                retry_after = exc.headers.get("Retry-After", "")
                try:
                    delay = max(float(retry_after), API_RATE_LIMIT_RETRY_DELAY_SECONDS)
                except ValueError:
                    delay = API_RATE_LIMIT_RETRY_DELAY_SECONDS
                print(
                    f"API: limite de pedidos atingido ({attempt}/{max_attempts}); "
                    f"a repetir em {format_duration(delay)}."
                )
                time.sleep(delay)
                continue
            if exc.code in {500, 502, 503, 504} and attempt < API_REQUEST_ATTEMPTS:
                delay = API_RETRY_DELAY_SECONDS * attempt
                print(
                    f"API: HTTP {exc.code} temporário ({attempt}/{API_REQUEST_ATTEMPTS}); "
                    f"a repetir em {format_duration(delay)}."
                )
                time.sleep(delay)
                continue
            raise RuntimeError(f"API {method} {path} falhou com HTTP {exc.code}: {details}") from exc
        except URLError as exc:
            if attempt == API_REQUEST_ATTEMPTS:
                raise RuntimeError(
                    f"API {method} {path} falhou após {attempt} tentativas: {exc.reason}"
                ) from exc
            print(
                f"API: tentativa {attempt}/{API_REQUEST_ATTEMPTS} falhou: {exc.reason}. "
                f"A repetir em {API_RETRY_DELAY_SECONDS}s."
            )
            time.sleep(API_RETRY_DELAY_SECONDS)

    raise RuntimeError(f"API {method} {path} falhou sem resposta.")


def list_coins(api_key: str, args: argparse.Namespace) -> list[dict[str, object]]:
    query_filter = {}
    for field in ("country", "name", "years"):
        value = getattr(args, field)
        if value:
            query_filter[field] = value

    query: dict[str, object] = {"limit": args.limit}
    if query_filter:
        query["q"] = json.dumps(query_filter, ensure_ascii=False)

    data = api_request("GET", "/entities/Coin", api_key, query=query)
    if not isinstance(data, list):
        raise RuntimeError(f"Resposta inesperada ao listar moedas: {data!r}")
    return [coin for coin in data if isinstance(coin, dict)]


def country_slug_candidates(country: str) -> list[str]:
    base = slugify(country)
    return COUNTRY_SLUG_ALIASES.get(base, [base])


def coin_slug_candidates(coin: dict[str, object]) -> set[str]:
    country = str(coin.get("country") or "")
    name = str(coin.get("name") or "")
    years = str(coin.get("years") or "")

    name_slug = slugify(name)
    year_slugs = [slugify(years)] if years else []
    year_slugs.extend(slugify(part) for part in re.split(r"[,;/]", years) if part.strip())
    year_slugs = [year_slug for year_slug in dict.fromkeys(year_slugs) if year_slug]

    candidates: set[str] = set()
    for country_slug in country_slug_candidates(country):
        if name_slug and year_slugs:
            for year_slug in year_slugs:
                candidates.add(f"{country_slug}-{name_slug}-{year_slug}")
        if name_slug:
            candidates.add(f"{country_slug}-{name_slug}")

    return candidates


def find_coins(api_key: str, args: argparse.Namespace) -> list[dict[str, object]]:
    if args.coin_id:
        data = api_request("GET", f"/entities/Coin/{args.coin_id}", api_key)
        if not isinstance(data, dict):
            raise RuntimeError(f"Resposta inesperada para coin-id {args.coin_id}: {data!r}")
        return [data]

    coins = list_coins(api_key, args)
    if not args.slug:
        return coins

    exact_matches = [coin for coin in coins if args.slug in coin_slug_candidates(coin)]

    if len(exact_matches) == 1:
        return exact_matches

    if not exact_matches and len(coins) == 1:
        return coins

    if not exact_matches:
        sample = "\n".join(
            f"- {coin.get('id')} | {coin.get('country')} | {coin.get('name')} | {coin.get('years')}"
            for coin in coins[:20]
        )
        raise RuntimeError(
            f"Não encontrei moeda compatível com slug '{args.slug}'. "
            f"Usa --coin-id ou filtros --country/--name/--years. Candidatas recebidas:\n{sample}"
        )

    sample = "\n".join(
        f"- {coin.get('id')} | {coin.get('country')} | {coin.get('name')} | {coin.get('years')}"
        for coin in exact_matches
    )
    raise RuntimeError(f"Mais do que uma moeda corresponde a '{args.slug}'. Usa --coin-id:\n{sample}")


class BrowserImageDownloader:
    """Reutiliza a sessão Chromium para os downloads uCoin que precisem dela."""

    def __init__(self, user_data_dir: str) -> None:
        self.user_data_dir = user_data_dir
        self.playwright = None
        self.context = None

    def _context_is_usable(self) -> bool:
        if self.context is None:
            return False
        try:
            return self.context.browser.is_connected()
        except Exception:  # noqa: BLE001
            return False

    def _start_context(self) -> None:
        if self._context_is_usable():
            return

        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Playwright não está instalado. Executa: python3 -m pip install playwright") from exc

        if self.playwright is None:
            self.playwright = sync_playwright().start()

        executable = which("chromium") or which("chromium-browser") or which("google-chrome") or which("google-chrome-stable")
        launch_options = {"executable_path": executable} if executable else {}
        self.context = self.playwright.chromium.launch_persistent_context(
            self.user_data_dir,
            headless=True,
            accept_downloads=True,
            ignore_https_errors=True,
            **launch_options,
        )
        print("Chromium: sessão iniciada; será reutilizada nos próximos downloads protegidos.")

    def _discard_context(self, wait_for_profile_release: bool) -> None:
        if self.context is not None:
            try:
                self.context.close()
            except Exception:  # noqa: BLE001
                pass
            self.context = None
        if wait_for_profile_release:
            # A profile directory can remain locked briefly after Chromium closes.
            time.sleep(15)

    def download(self, url: str, destination: Path) -> bool:
        destination.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, BROWSER_DOWNLOAD_ATTEMPTS + 1):
            page = None
            try:
                self._start_context()
                page = self.context.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                if response is None:
                    raise RuntimeError("o servidor não devolveu resposta")
                content_type = response.headers.get("content-type", "")
                body = response.body()
                if 200 <= response.status < 300 and "image" in content_type.lower() and body:
                    destination.write_bytes(body)
                    return True
                raise RuntimeError(f"resposta sem imagem válida ({response.status}, {content_type or 'sem content-type'})")
            except Exception as exc:  # noqa: BLE001
                details = str(exc).splitlines()[0] or type(exc).__name__
                session_lost = not self._context_is_usable()
                if session_lost:
                    print("Chromium: sessão indisponível; a reiniciar o perfil antes de continuar.")
                    self._discard_context(wait_for_profile_release=True)
                if attempt == BROWSER_DOWNLOAD_ATTEMPTS:
                    print(f"Chromium: falhou após {attempt} tentativas: {details}")
                    return False
                print(
                    f"Chromium: tentativa {attempt}/{BROWSER_DOWNLOAD_ATTEMPTS} falhou: {details}. "
                    f"A repetir em {BROWSER_RETRY_DELAY_SECONDS}s."
                )
                time.sleep(BROWSER_RETRY_DELAY_SECONDS)
            finally:
                if page is not None:
                    try:
                        page.close()
                    except Exception:  # noqa: BLE001
                        pass
        return False

    def close(self) -> None:
        self._discard_context(wait_for_profile_release=False)
        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self.playwright = None


def download_image(
    url: str,
    destination: Path,
    overwrite: bool,
    browser_profile: str,
    use_browser_fallback: bool,
    browser_downloader: BrowserImageDownloader | None = None,
) -> str:
    if destination.exists() and not overwrite:
        return "exists"

    if "i.ucoin.net" in url.lower():
        if download_image_with_curl(url, destination):
            return "downloaded"
        if use_browser_fallback and download_image_with_browser(url, destination, browser_profile, browser_downloader):
            return "downloaded-browser"
        raise RuntimeError(f"Download bloqueado pelo i.ucoin.net: {url}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, IMAGE_DOWNLOAD_ATTEMPTS + 1):
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=60) as response:
                content_type = response.headers.get("Content-Type", "")
                if "image" not in content_type.lower():
                    raise RuntimeError(f"URL não parece imagem ({content_type}): {url}")
                save_image_as_jpeg(response.read(), destination)
            return "downloaded"
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == IMAGE_DOWNLOAD_ATTEMPTS:
                raise RuntimeError(f"Download falhou com HTTP {exc.code}: {url}") from exc
            delay = IMAGE_DOWNLOAD_RETRY_DELAY_SECONDS * attempt
        except URLError as exc:
            if attempt == IMAGE_DOWNLOAD_ATTEMPTS:
                raise RuntimeError(
                    f"Download falhou após {attempt} tentativas ({exc.reason}): {url}"
                ) from exc
            delay = IMAGE_DOWNLOAD_RETRY_DELAY_SECONDS * attempt
        print(
            f"Download: tentativa {attempt}/{IMAGE_DOWNLOAD_ATTEMPTS} falhou; "
            f"a repetir em {format_duration(delay)}."
        )
        time.sleep(delay)

    raise RuntimeError(f"Download falhou sem resposta: {url}")


def save_image_as_jpeg(data: bytes, destination: Path) -> None:
    """Write downloaded image bytes as a real JPEG, converting when needed."""
    if data.startswith(b"\xff\xd8\xff"):
        destination.write_bytes(data)
        return

    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "A imagem não é JPEG. Instala Pillow para a converter: python3 -m pip install Pillow"
        ) from exc

    with Image.open(BytesIO(data)) as image:
        if image.mode in {"RGBA", "LA"}:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        image.save(destination, format="JPEG", quality=95, optimize=True)


def download_image_with_curl(url: str, destination: Path) -> bool:
    curl_bin = which("curl")
    if not curl_bin:
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            curl_bin,
            "-fL",
            "--connect-timeout",
            "30",
            "--max-time",
            "90",
            "-A",
            "Mozilla/5.0",
            "-H",
            "Accept: image/*,*/*;q=0.8",
            "-o",
            str(destination),
            url,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False
    return destination.exists() and destination.stat().st_size > 0


def download_image_with_browser(
    url: str,
    destination: Path,
    user_data_dir: str,
    browser_downloader: BrowserImageDownloader | None = None,
) -> bool:
    owns_downloader = browser_downloader is None
    downloader = browser_downloader or BrowserImageDownloader(user_data_dir)
    try:
        return downloader.download(url, destination)
    finally:
        if owns_downloader:
            downloader.close()


def parse_links_file(path: Path) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    current_slug = ""
    if not path.exists():
        return entries

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        slug_match = re.match(r"^([^\s:][^:]*):$", line)
        if slug_match:
            current_slug = slug_match.group(1).strip()
            entries.setdefault(current_slug, {})
            continue
        link_match = re.match(r"^\s+(frente|tras):\s+(https?://\S+)\s*$", line)
        if current_slug and link_match:
            entries[current_slug][link_match.group(1)] = link_match.group(2)
    return entries


def write_country_links(
    folder: Path,
    slug: str,
    links: dict[str, str],
    filename: str = INTERNAL_LINKS_FILENAME,
) -> None:
    path = folder / filename
    entries = parse_links_file(path)
    entries[slug] = {"frente": links["frente"], "tras": links["tras"]}

    lines: list[str] = []
    for entry_slug in sorted(entries):
        entry_links = entries[entry_slug]
        lines.append(f"{entry_slug}:")
        if "frente" in entry_links:
            lines.append(f"  frente: {entry_links['frente']}")
        if "tras" in entry_links:
            lines.append(f"  tras: {entry_links['tras']}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def mutable_coin_payload(coin: dict[str, object], frente_url: str, tras_url: str) -> dict[str, object]:
    payload = {key: value for key, value in coin.items() if key not in READ_ONLY_FIELDS}
    payload["image_frente"] = frente_url
    payload["image_verso"] = tras_url
    return payload


def run_git(command: list[str]) -> str:
    # No WSL, the Windows Git Credential Manager may hold the GitHub session
    # while the Linux credential cache is empty. Prefer its git.exe when it is
    # available, so an automatic push has the same authentication as a manual
    # push from Windows Git.
    git_executable = which("git.exe") if "microsoft" in os.uname().release.lower() else None
    git_executable = git_executable or "git"
    proc = subprocess.run([git_executable, *command], capture_output=True, text=True)
    if proc.returncode != 0:
        details = (proc.stderr or proc.stdout or "erro desconhecido").strip()
        raise RuntimeError(f"{git_executable} {' '.join(command)} falhou: {details}")
    return proc.stdout.strip()


def git_has_changes() -> bool:
    return bool(run_git(["status", "--porcelain"]))


def git_commit_and_push(message: str) -> None:
    if not git_has_changes():
        print("Git: sem alterações para commit/push.")
        return

    print("Git: add .")
    run_git(["add", "."])

    if not git_has_changes():
        print("Git: sem alterações staged para commit.")
        return

    print(f"Git: commit -m {message!r}")
    run_git(["commit", "-m", message])
    print("Git: push")
    run_git(["push"])
    print("Git: push concluído.")


def main() -> int:
    args = parse_args()
    load_dotenv()
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Define a API key em .env ou antes de correr: export {args.api_key_env}=\"...\"", file=sys.stderr)
        return 2

    if not args.coin_id and not args.country:
        print("Indica --country para listar moedas, ou --coin-id para uma moeda específica.", file=sys.stderr)
        return 2

    if args.name and not args.years and not args.coin_id:
        print("Quando usas --name, indica também --years para evitar apanhar a moeda errada.", file=sys.stderr)
        return 2

    if args.api_only and (args.download_current or args.download_only):
        print("--api-only não pode ser usado com --download-current ou --download-only.", file=sys.stderr)
        return 2

    coins = find_coins(api_key, args)
    if not coins:
        print("Nenhuma moeda encontrada para os filtros indicados.", file=sys.stderr)
        return 2

    pending_updates: list[tuple[str, dict[str, object], str]] = []
    coin_slugs = unique_coin_slugs(coins, args.slug)

    total_coins = len(coins)
    started_at = time.monotonic()
    coin_started_at: float | None = None
    recent_coin_durations: deque[float] = deque(maxlen=10)
    browser_downloader = None
    if (args.download_current or args.download_only) and not args.no_ucoin_browser_fallback:
        browser_downloader = BrowserImageDownloader(args.ucoin_browser_profile)
        # Also release the persistent profile if an unexpected error stops the run.
        atexit.register(browser_downloader.close)

    print(f"Moedas encontradas: {total_coins}")
    for index, coin in enumerate(coins, start=1):
        now = time.monotonic()
        if coin_started_at is not None:
            recent_coin_durations.append(now - coin_started_at)
        coin_started_at = now

        completed = index - 1
        percent = completed / total_coins * 100
        elapsed = now - started_at
        if len(recent_coin_durations) >= 3:
            eta = sum(recent_coin_durations) / len(recent_coin_durations) * (total_coins - completed)
            eta_text = f"ETA imagens: ~{format_duration(eta)}"
        else:
            eta_text = "ETA imagens: a calcular"
        if not args.api_only:
            print(
                f"\n[Progresso imagens: {completed}/{total_coins} ({percent:.0f}%) | "
                f"decorrido: {format_duration(elapsed)} | {eta_text}]"
            )

        coin_id = str(coin.get("id") or "")
        if not coin_id:
            print(f"Moeda encontrada sem id: {coin!r}", file=sys.stderr)
            return 2

        coin_slug = coin_slugs[coin_id]
        target_links = generated_image_links(coin, args, coin_slug)

        if not args.api_only:
            print(f"Moeda: {coin_label(coin)}")

        source_links = {
            "frente": str(coin.get("image_frente") or ""),
            "tras": str(coin.get("image_verso") or ""),
        }
        if source_links == target_links:
            continue
        has_ucoin_links = "i.ucoin.net" in source_links["frente"].lower() and "i.ucoin.net" in source_links["tras"].lower()
        if not args.include_without_ucoin and not has_ucoin_links:
            print("Saltada: não tem links i.ucoin.net nos dois lados; fica como está.")
            continue

        folder = normal_country_path(
            str(coin.get("country") or args.country or ""),
            str(coin.get("continent") or ""),
            args.country_folder,
        )
        target_files = {
            "frente": folder / "frente" / f"{coin_slug}.jpg",
            "tras": folder / "tras" / f"{coin_slug}.jpg",
        }

        if args.download_current or args.download_only:
            for side, api_field, subdir in (("frente", "image_frente", "frente"), ("tras", "image_verso", "tras")):
                source_url = str(coin.get(api_field) or "")
                destination = target_files[side]
                if not source_url:
                    print(f"Download {side}: sem URL atual na API")
                    continue
                if (args.apply or args.download_only) and not args.api_only:
                    status = download_image(
                        source_url,
                        destination,
                        args.overwrite_images,
                        args.ucoin_browser_profile,
                        not args.no_ucoin_browser_fallback,
                        browser_downloader,
                    )
                    print(f"Download {side}: {status} -> {destination}")
                else:
                    print(f"Download {side}: dry-run -> {destination}")

        if args.apply and not args.download_current and not args.download_only:
            missing_sides = [side for side, path in target_files.items() if not path.exists()]
            if missing_sides:
                print(f"Saltada: imagens locais em falta ({', '.join(missing_sides)}); fica como está.")
                continue

        if (args.apply or args.download_only) and not args.api_only:
            write_country_links(folder, coin_slug, target_links)
            if source_links["frente"] and source_links["tras"]:
                write_country_links(folder, coin_slug, source_links, EXTERNAL_LINKS_FILENAME)
                print(f"Links externos: atualizado -> {folder / EXTERNAL_LINKS_FILENAME}")
            else:
                print("Links externos: mantido, porque falta pelo menos um URL de origem")
            print(f"Links internos: atualizado -> {folder / INTERNAL_LINKS_FILENAME}")

        if args.download_only:
            continue

        if not args.apply:
            continue

        pending_updates.append(
            (coin_id, mutable_coin_payload(coin, target_links["frente"], target_links["tras"]), coin_label(coin))
        )

    if browser_downloader is not None:
        browser_downloader.close()

    should_git_push = (args.apply or args.download_only) and not args.no_git_push and not args.api_only
    if should_git_push:
        git_commit_and_push(args.git_commit_message)

    total_updates = len(pending_updates)
    api_started_at = time.monotonic()
    api_coin_started_at: float | None = None
    recent_api_durations: deque[float] = deque(maxlen=10)
    for index, (coin_id, payload, label) in enumerate(pending_updates, start=1):
        now = time.monotonic()
        if api_coin_started_at is not None:
            recent_api_durations.append(now - api_coin_started_at)
        api_coin_started_at = now
        api_request("PUT", f"/entities/Coin/{coin_id}", api_key, payload=payload)
        updated_coin = api_request("GET", f"/entities/Coin/{coin_id}", api_key)
        if not isinstance(updated_coin, dict):
            raise RuntimeError(f"Resposta inesperada ao verificar moeda atualizada: {updated_coin!r}")

        completed = index
        percent = completed / total_updates * 100
        elapsed = time.monotonic() - api_started_at
        if len(recent_api_durations) >= 3:
            eta = sum(recent_api_durations) / len(recent_api_durations) * (total_updates - completed)
            eta_text = f"estimativa: ~{format_duration(eta)}"
        else:
            eta_text = "estimativa: a calcular"
        print(
            f"[Progresso API: {completed}/{total_updates} ({percent:.0f}%) | "
            f"decorrido: {format_duration(elapsed)} | {eta_text}]"
        )
        print(f"✓ API atualizada e verificada — {label}")

    if args.download_only:
        print("\nDownload-only: imagens descarregadas, nenhuma alteração foi enviada para a API.")
    elif not args.apply:
        print("\nDry-run: nenhuma alteração foi enviada para a API. Usa --apply para atualizar.")
    else:
        completed_updates = total_updates if args.api_only else total_coins
        total_for_summary = total_updates if args.api_only else total_coins
        progress_label = "API" if args.api_only else "imagens"
        print(
            f"\nProgresso {progress_label} concluído: {completed_updates}/{total_for_summary} (100%) | "
            f"tempo total: {format_duration(time.monotonic() - started_at)}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
