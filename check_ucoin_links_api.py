#!/usr/bin/env python3
"""Lista moedas na API que ainda apontam para i.ucoin.net."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE_URL = "https://track-coin-collection.base44.app/api"
API_KEY_ENV = "ALL_COINS_API_KEY"
UCOIN_DOMAIN = "i.ucoin.net"


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verifica países/moedas que ainda usam links i.ucoin.net na API.")
    parser.add_argument("--api-key-env", default=API_KEY_ENV, help="Nome da variável de ambiente com a API key.")
    parser.add_argument("--limit", type=int, default=5000, help="Máximo de moedas a consultar.")
    parser.add_argument("--country", help="Filtra um país específico, opcional.")
    parser.add_argument("--json", action="store_true", help="Imprime o resultado em JSON.")
    return parser.parse_args()


def api_request(path: str, api_key: str, query: dict[str, object]) -> object:
    url = f"{API_BASE_URL}{path}?{urlencode(query)}"
    request = Request(url, headers={"api_key": api_key, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API GET {path} falhou com HTTP {exc.code}: {details}") from exc
    except URLError as exc:
        raise RuntimeError(f"API GET {path} falhou: {exc.reason}") from exc


def list_coins(api_key: str, limit: int, country: str | None = None) -> list[dict[str, object]]:
    query: dict[str, object] = {"limit": limit}
    if country:
        query["q"] = json.dumps({"country": country}, ensure_ascii=False)

    data = api_request("/entities/Coin", api_key, query)
    if not isinstance(data, list):
        raise RuntimeError(f"Resposta inesperada ao listar moedas: {data!r}")
    return [coin for coin in data if isinstance(coin, dict)]


def ucoin_sides(coin: dict[str, object]) -> list[str]:
    sides = []
    for side, field in (("frente", "image_frente"), ("verso", "image_verso")):
        if UCOIN_DOMAIN in str(coin.get(field) or "").lower():
            sides.append(side)
    return sides


def build_report(coins: list[dict[str, object]]) -> dict[str, object]:
    country_totals: dict[str, int] = defaultdict(int)
    countries: dict[str, list[dict[str, object]]] = defaultdict(list)

    for coin in coins:
        country = str(coin.get("country") or "(sem pais)")
        country_totals[country] += 1
        sides = ucoin_sides(coin)
        if not sides:
            continue
        countries[country].append(
            {
                "id": coin.get("id"),
                "name": coin.get("name"),
                "years": coin.get("years"),
                "sides": sides,
            }
        )

    return {
        "total_coins": len(coins),
        "countries": len(country_totals),
        "countries_with_ucoin": len(countries),
        "coins_with_ucoin": sum(len(rows) for rows in countries.values()),
        "by_country": dict(sorted(countries.items())),
        "country_totals": dict(sorted(country_totals.items())),
    }


def print_report(report: dict[str, object]) -> None:
    by_country = report["by_country"]
    country_totals = report["country_totals"]
    assert isinstance(by_country, dict)
    assert isinstance(country_totals, dict)

    print(f"total_coins={report['total_coins']}")
    print(f"countries={report['countries']}")
    print(f"countries_with_ucoin={report['countries_with_ucoin']}")
    print(f"coins_with_ucoin={report['coins_with_ucoin']}")

    if not by_country:
        print("\nOK: nenhuma moeda ainda aponta para i.ucoin.net.")
        return

    print("")
    for country, rows in by_country.items():
        total = country_totals.get(country, "?")
        print(f"{country}: {len(rows)} / {total}")
        for row in rows:
            sides = ",".join(row["sides"])
            print(f"  - {row['name']} | {row['years']} | {row['id']} | {sides}")
        print("")


def main() -> int:
    load_dotenv()
    args = parse_args()
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f'Define a API key antes de correr: export {args.api_key_env}="..."', flush=True)
        return 2

    coins = list_coins(api_key, args.limit, args.country)
    report = build_report(coins)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 1 if report["coins_with_ucoin"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
