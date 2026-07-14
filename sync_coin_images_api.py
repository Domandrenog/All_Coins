#!/usr/bin/env python3
"""Atualiza URLs de imagens de moedas na API para apontarem para o raw do GitHub."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from shutil import which
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

API_BASE_URL = "https://track-coin-collection.base44.app/api"
API_KEY_ENV = "ALL_COINS_API_KEY"
DEFAULT_RAW_BASE_URL = "https://raw.githubusercontent.com/Domandrenog/All_Coins/main"
READ_ONLY_FIELDS = {"id", "created_date", "updated_date", "created_by_id"}

COUNTRY_SLUG_ALIASES = {
    "polonia": ["polonia", "poland"],
    "poland": ["poland", "polonia"],
    "bielorrussia": ["bielorrussia", "belarus"],
    "belarus": ["belarus", "bielorrussia"],
    "china": ["china"],
    "coreia-do-sul": ["coreia-do-sul", "south-korea"],
    "south-korea": ["south-korea", "coreia-do-sul"],
    "emirados-arabes-unidos": ["emirados-arabes-unidos", "united-arab-emirates"],
    "united-arab-emirates": ["united-arab-emirates", "emirados-arabes-unidos"],
    "japao": ["japao", "japan"],
    "japan": ["japan", "japao"],
    "macau": ["macau"],
    "malasia": ["malasia", "malaysia"],
    "malaysia": ["malaysia", "malasia"],
    "singapura": ["singapura", "singapore"],
    "singapore": ["singapore", "singapura"],
    "sri-lanka": ["sri-lanka"],
    "tailandia": ["tailandia", "thailand"],
    "thailand": ["thailand", "tailandia"],
    "hong-kong": ["hong-kong"],
    "taiwan": ["taiwan"],
}

COUNTRY_FILE_SLUGS = {
    "polonia": "poland",
    "poland": "poland",
    "bielorrussia": "belarus",
    "belarus": "belarus",
    "china": "china",
    "coreia-do-sul": "south-korea",
    "south-korea": "south-korea",
    "emirados-arabes-unidos": "united-arab-emirates",
    "united-arab-emirates": "united-arab-emirates",
    "japao": "japan",
    "japan": "japan",
    "macau": "macau",
    "malasia": "malaysia",
    "malaysia": "malaysia",
    "singapura": "singapore",
    "singapore": "singapore",
    "sri-lanka": "sri-lanka",
    "tailandia": "thailand",
    "thailand": "thailand",
    "hong-kong": "hong-kong",
    "taiwan": "taiwan",
}

COUNTRY_FOLDERS = {
    "polonia": "Polonia",
    "poland": "Polonia",
    "bielorrussia": "Bielorrussia",
    "belarus": "Bielorrussia",
    "china": "China",
    "coreia-do-sul": "CoreiaDoSul",
    "south-korea": "CoreiaDoSul",
    "emirados-arabes-unidos": "EmiradosArabesUnidos",
    "united-arab-emirates": "EmiradosArabesUnidos",
    "japao": "Japao",
    "japan": "Japao",
    "macau": "Macau",
    "malasia": "Malasia",
    "malaysia": "Malasia",
    "singapura": "Singapura",
    "singapore": "Singapura",
    "sri-lanka": "SriLanka",
    "tailandia": "Tailandia",
    "thailand": "Tailandia",
    "hong-kong": "HongKong",
    "taiwan": "Taiwan",
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
    parser.add_argument("--country-folder", help="Pasta do país no repo, ex.: Polonia. Por defeito é inferida do país.")
    parser.add_argument("--raw-base-url", default=DEFAULT_RAW_BASE_URL, help="Base raw do GitHub.")
    parser.add_argument("--limit", type=int, default=1000, help="Máximo de moedas a listar quando não há coin-id.")
    parser.add_argument("--api-key-env", default=API_KEY_ENV, help="Nome da variável de ambiente com a API key.")
    parser.add_argument("--download-current", action="store_true", help="Descarrega as imagens atuais da API antes de atualizar.")
    parser.add_argument("--download-only", action="store_true", help="Descarrega as imagens atuais, mas não atualiza a API.")
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


def country_folder(country: str, explicit_folder: str | None) -> str:
    if explicit_folder:
        return explicit_folder.strip("/")
    country_slug = slugify(country)
    return COUNTRY_FOLDERS.get(country_slug, country)


def coin_file_slug(coin: dict[str, object], manual_slug: str | None = None) -> str:
    if manual_slug:
        return manual_slug

    image_slug = image_file_slug(str(coin.get("image_frente") or coin.get("image_verso") or ""))
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


def image_file_slug(url: str) -> str:
    if not url:
        return ""

    filename = Path(unquote(urlparse(url).path)).name
    stem = Path(filename).stem
    return slugify(stem.replace("_", "-"))


def generated_image_links(coin: dict[str, object], args: argparse.Namespace) -> dict[str, str]:
    folder = country_folder(str(coin.get("country") or args.country or ""), args.country_folder)
    slug = coin_file_slug(coin, args.slug)
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

    try:
        with urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
            return json.loads(response_body) if response_body else {}
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API {method} {path} falhou com HTTP {exc.code}: {details}") from exc
    except URLError as exc:
        raise RuntimeError(f"API {method} {path} falhou: {exc.reason}") from exc


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


def download_image(url: str, destination: Path, overwrite: bool, browser_profile: str, use_browser_fallback: bool) -> str:
    if destination.exists() and not overwrite:
        return "exists"

    if "i.ucoin.net" in url.lower():
        if download_image_with_curl(url, destination):
            return "downloaded"
        if use_browser_fallback and download_image_with_browser(url, destination, browser_profile):
            return "downloaded-browser"
        raise RuntimeError(f"Download bloqueado pelo i.ucoin.net: {url}")

    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(request, timeout=60) as response:
        content_type = response.headers.get("Content-Type", "")
        if "image" not in content_type.lower():
            raise RuntimeError(f"URL não parece imagem ({content_type}): {url}")
        destination.write_bytes(response.read())
    return "downloaded"


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


def download_image_with_browser(url: str, destination: Path, user_data_dir: str) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Playwright não está instalado. Executa: python3 -m pip install playwright") from exc

    executable = which("chromium") or which("chromium-browser") or which("google-chrome") or which("google-chrome-stable")
    launch_options = {"executable_path": executable} if executable else {}
    destination.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir,
                headless=True,
                accept_downloads=True,
                ignore_https_errors=True,
                **launch_options,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Não consegui abrir Chromium/Playwright: {str(exc).splitlines()[0]}") from exc

        page = context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            if response is None:
                return False
            content_type = response.headers.get("content-type", "")
            body = response.body()
            if 200 <= response.status < 300 and "image" in content_type.lower() and body:
                destination.write_bytes(body)
                return True
            return False
        finally:
            context.close()


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


def write_country_links(folder: Path, slug: str, links: dict[str, str], filename: str = "links.txt") -> None:
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
    proc = subprocess.run(["git", *command], capture_output=True, text=True)
    if proc.returncode != 0:
        details = (proc.stderr or proc.stdout or "erro desconhecido").strip()
        raise RuntimeError(f"git {' '.join(command)} falhou: {details}")
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
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Define a API key antes de correr: export {args.api_key_env}=\"...\"", file=sys.stderr)
        return 2

    if not args.coin_id and not args.country:
        print("Indica --country para listar moedas, ou --coin-id para uma moeda específica.", file=sys.stderr)
        return 2

    if args.name and not args.years and not args.coin_id:
        print("Quando usas --name, indica também --years para evitar apanhar a moeda errada.", file=sys.stderr)
        return 2

    coins = find_coins(api_key, args)
    if not coins:
        print("Nenhuma moeda encontrada para os filtros indicados.", file=sys.stderr)
        return 2

    pending_updates: list[tuple[str, dict[str, object]]] = []

    print(f"Moedas encontradas: {len(coins)}")
    for coin in coins:
        coin_id = str(coin.get("id") or "")
        if not coin_id:
            print(f"Moeda encontrada sem id: {coin!r}", file=sys.stderr)
            return 2

        target_links = generated_image_links(coin, args)
        coin_slug = coin_file_slug(coin, args.slug)

        print("")
        print(f"Moeda API: {coin_id} | {coin.get('country')} | {coin.get('name')} | {coin.get('years')}")
        print(f"Atual frente: {coin.get('image_frente') or ''}")
        print(f"Nova frente:  {target_links['frente']}")
        print(f"Atual tras:   {coin.get('image_verso') or ''}")
        print(f"Nova tras:    {target_links['tras']}")

        source_links = {
            "frente": str(coin.get("image_frente") or ""),
            "tras": str(coin.get("image_verso") or ""),
        }
        has_ucoin_links = "i.ucoin.net" in source_links["frente"].lower() and "i.ucoin.net" in source_links["tras"].lower()
        if not args.include_without_ucoin and not has_ucoin_links:
            print("Saltada: não tem links i.ucoin.net nos dois lados; fica como está.")
            continue

        folder = Path(country_folder(str(coin.get("country") or args.country or ""), args.country_folder))

        if args.download_current or args.download_only:
            for side, api_field, subdir in (("frente", "image_frente", "frente"), ("tras", "image_verso", "tras")):
                source_url = str(coin.get(api_field) or "")
                destination = folder / subdir / f"{coin_slug}.jpg"
                if not source_url:
                    print(f"Download {side}: sem URL atual na API")
                    continue
                if args.apply or args.download_only:
                    status = download_image(
                        source_url,
                        destination,
                        args.overwrite_images,
                        args.ucoin_browser_profile,
                        not args.no_ucoin_browser_fallback,
                    )
                    print(f"Download {side}: {status} -> {destination}")
                else:
                    print(f"Download {side}: dry-run -> {destination}")

        if args.apply or args.download_only:
            write_country_links(folder, coin_slug, target_links)
            if "i.ucoin.net" in source_links["frente"].lower() or "i.ucoin.net" in source_links["tras"].lower():
                write_country_links(folder, coin_slug, source_links, "links-ucoin.txt")
                print(f"Links uCoin: atualizado -> {folder / 'links-ucoin.txt'}")
            else:
                print("Links uCoin: mantido, porque a API já não aponta para i.ucoin.net")
            print(f"Links: atualizado -> {folder / 'links.txt'}")

        if args.download_only:
            continue

        if not args.apply:
            continue

        pending_updates.append((coin_id, mutable_coin_payload(coin, target_links["frente"], target_links["tras"])))

    should_git_push = (args.apply or args.download_only) and not args.no_git_push
    if should_git_push:
        git_commit_and_push(args.git_commit_message)

    for coin_id, payload in pending_updates:
        api_request("PUT", f"/entities/Coin/{coin_id}", api_key, payload=payload)
        updated_coin = api_request("GET", f"/entities/Coin/{coin_id}", api_key)
        if not isinstance(updated_coin, dict):
            raise RuntimeError(f"Resposta inesperada ao verificar moeda atualizada: {updated_coin!r}")

        print("API atualizada e verificada:")
        print(f"image_frente: {updated_coin.get('image_frente') or ''}")
        print(f"image_verso:  {updated_coin.get('image_verso') or ''}")

    if args.download_only:
        print("\nDownload-only: imagens descarregadas, nenhuma alteração foi enviada para a API.")
    elif not args.apply:
        print("\nDry-run: nenhuma alteração foi enviada para a API. Usa --apply para atualizar.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)