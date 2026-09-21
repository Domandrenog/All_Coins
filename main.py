#!/usr/bin/env python3
"""Menu simples para preparar imagens e migrar os URLs na Base44."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.sync_coin_images_api import country_folder


ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
SYNC_SCRIPT = SCRIPTS / "sync_coin_images_api.py"
CHECK_SCRIPT = SCRIPTS / "check_ucoin_links_api.py"
CATALOG_SYNC_SCRIPT = SCRIPTS / "sync_catalog_images_api.py"
CATALOG_CHECK_SCRIPT = SCRIPTS / "check_catalog_links_api.py"

CATALOG_LABELS = {
    "normal": "Moedas normais",
    "collection": "Moedas de coleção",
    "notes": "Notas",
}


def run(command: list[str], *, accepted_codes: set[int] | None = None) -> bool:
    print(f"\n$ {' '.join(command)}\n")
    result = subprocess.run(command, cwd=ROOT)
    return result.returncode in (accepted_codes or {0})


def catalog_command(script: Path, catalog: str) -> list[str]:
    command = [sys.executable, str(script)]
    if catalog != "normal":
        command.extend(["--catalog", catalog])
    return command


def scripts_for_catalog(catalog: str) -> tuple[Path, Path]:
    if catalog == "normal":
        return SYNC_SCRIPT, CHECK_SCRIPT
    return CATALOG_SYNC_SCRIPT, CATALOG_CHECK_SCRIPT


def choose_catalog(*, allow_all: bool = False) -> list[str] | None:
    print("\n1. Moedas normais\n2. Moedas de coleção\n3. Notas")
    if allow_all:
        print("4. Todas as categorias")
    print("0. Voltar")
    choice = input("Escolha a categoria: ").strip()
    choices = {"1": "normal", "2": "collection", "3": "notes"}
    if allow_all and choice == "4":
        return list(CATALOG_LABELS)
    if choice == "0":
        return None
    catalog = choices.get(choice)
    if not catalog:
        print("Opção inválida.")
        return None
    return [catalog]


def read_pending_report(catalog: str) -> dict[str, object] | None:
    _, check_script = scripts_for_catalog(catalog)
    command = catalog_command(check_script, catalog)
    command.append("--json")
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode not in {0, 1}:
        print(result.stderr or result.stdout or "Não foi possível consultar a API.")
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print("A API devolveu um relatório inválido.")
        return None


def choose_countries(catalog: str) -> list[str] | None:
    print("\n1. Um país\n2. Todos os países ainda pendentes\n0. Voltar")
    choice = input("Escolha o âmbito: ").strip()
    if choice == "0":
        return None
    if choice == "1":
        country = input("Nome exato do país na API: ").strip()
        return [country] if country else None
    if choice != "2":
        print("Opção inválida.")
        return None

    report = read_pending_report(catalog)
    if report is None:
        return None
    pending_key = "full_by_country" if catalog == "normal" else "pending_by_country"
    pending_by_country = report.get(pending_key, {})
    if not isinstance(pending_by_country, dict):
        print("O relatório não contém países pendentes válidos.")
        return None
    countries = sorted(str(country) for country in pending_by_country)
    if not countries:
        print("Não há países com imagens uCoin nos dois lados para processar.")
        return None
    print(f"Países a processar ({len(countries)}): {', '.join(countries)}")
    return countries


def confirm(message: str) -> bool:
    return input(f"{message}\nEscreve ATUALIZAR para continuar: ").strip() == "ATUALIZAR"


def worktree_has_only_country_changes(countries: list[str], catalog: str) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr or "Não foi possível verificar o estado do Git.")
        return False
    allowed_folders = {country_folder(country, None) for country in countries}
    changed_paths = [line[3:] for line in result.stdout.splitlines() if len(line) > 3]

    def is_allowed_country_path(path: str) -> bool:
        parts = Path(path).parts
        return (
            len(parts) >= 5
            and parts[:2] == ("fotos", "paises")
            and parts[3] in allowed_folders
            and parts[4] == catalog
        )

    if any(not is_allowed_country_path(path) for path in changed_paths):
        print(
            "O repositório tem alterações locais fora dos países selecionados. Faz commit ou "
            "guarda-as de outra forma antes da migração completa."
        )
        return False
    return True


def process_countries(countries: list[str], mode: str, catalog: str) -> None:
    if mode == "full":
        arguments = ["--download-current", "--apply"]
        confirmation = "Descarrega imagens, cria um commit/push por país e atualiza a Base44."
    elif mode == "download":
        arguments = ["--download-only", "--no-git-push"]
        confirmation = "Descarrega imagens e atualiza links locais; não altera a Base44 nem faz push."
    else:
        arguments = ["--api-only", "--apply", "--no-git-push"]
        confirmation = "Altera image_frente e image_verso na Base44; não descarrega imagens nem faz push."

    print(f"\nCategoria: {CATALOG_LABELS[catalog]}")
    print(f"Países selecionados: {', '.join(countries)}")
    if mode == "full" and not worktree_has_only_country_changes(countries, catalog):
        return
    if mode != "download" and not confirm(confirmation):
        print("Operação cancelada.")
        return

    for index, country in enumerate(countries, start=1):
        print(f"\n===== [{index}/{len(countries)}] {country} =====")
        sync_script, _ = scripts_for_catalog(catalog)
        command = catalog_command(sync_script, catalog)
        command.extend(["--country", country, *arguments])
        if mode == "full":
            command.extend(["--git-commit-message", f"Add {country} {catalog} images"])
        if not run(command):
            print(f"Processamento interrompido em {country}. Corrige o erro antes de continuar.")
            return

    print("\nOperação concluída.")


def print_menu() -> None:
    print(
        "\n=== All Coins ===\n"
        "1. Verificar toda a API\n"
        "2. Trocar imagens e atualizar a Base44\n"
        "3. Descarregar imagens\n"
        "4. Trocar URLs na Base44\n"
        "0. Sair"
    )


def main() -> int:
    while True:
        print_menu()
        choice = input("Escolha uma opção: ").strip()
        if choice == "0":
            return 0
        if choice == "1":
            catalogs = choose_catalog(allow_all=True)
            if catalogs:
                for catalog in catalogs:
                    print(f"\n===== {CATALOG_LABELS[catalog]} =====")
                    _, check_script = scripts_for_catalog(catalog)
                    run(catalog_command(check_script, catalog), accepted_codes={0, 1})
            continue
        modes = {"2": "full", "3": "download", "4": "api"}
        if choice not in modes:
            print("Opção inválida.")
            continue
        catalogs = choose_catalog()
        if not catalogs:
            continue
        catalog = catalogs[0]
        countries = choose_countries(catalog)
        if countries:
            process_countries(countries, modes[choice], catalog)


if __name__ == "__main__":
    raise SystemExit(main())
