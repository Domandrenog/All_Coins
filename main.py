#!/usr/bin/env python3
"""Menu simples para preparar imagens e migrar os URLs na Base44."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
SYNC_SCRIPT = SCRIPTS / "sync_coin_images_api.py"
CHECK_SCRIPT = SCRIPTS / "check_ucoin_links_api.py"


def run(command: list[str], *, accepted_codes: set[int] | None = None) -> bool:
    print(f"\n$ {' '.join(command)}\n")
    result = subprocess.run(command, cwd=ROOT)
    return result.returncode in (accepted_codes or {0})


def read_pending_report() -> dict[str, object] | None:
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), "--json"], cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode not in {0, 1}:
        print(result.stderr or result.stdout or "Não foi possível consultar a API.")
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print("A API devolveu um relatório inválido.")
        return None


def choose_countries() -> list[str] | None:
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

    report = read_pending_report()
    if report is None:
        return None
    full_by_country = report.get("full_by_country", {})
    if not isinstance(full_by_country, dict):
        print("O relatório não contém países pendentes válidos.")
        return None
    countries = sorted(str(country) for country in full_by_country)
    if not countries:
        print("Não há países com imagens uCoin nos dois lados para processar.")
        return None
    print(f"Países a processar ({len(countries)}): {', '.join(countries)}")
    return countries


def confirm(message: str) -> bool:
    return input(f"{message}\nEscreve ATUALIZAR para continuar: ").strip() == "ATUALIZAR"


def worktree_is_clean() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr or "Não foi possível verificar o estado do Git.")
        return False
    if result.stdout.strip():
        print(
            "O repositório tem alterações locais. Faz commit, guarda-as de outra forma, "
            "ou usa as operações separadas antes da migração completa."
        )
        return False
    return True


def process_countries(countries: list[str], mode: str) -> None:
    if mode == "full":
        arguments = ["--download-current", "--apply"]
        confirmation = "Descarrega imagens, cria um commit/push por país e atualiza a Base44."
    elif mode == "download":
        arguments = ["--download-only", "--no-git-push"]
        confirmation = "Descarrega imagens e atualiza links locais; não altera a Base44 nem faz push."
    else:
        arguments = ["--api-only", "--apply", "--no-git-push"]
        confirmation = "Altera image_frente e image_verso na Base44; não descarrega imagens nem faz push."

    print(f"\nPaíses selecionados: {', '.join(countries)}")
    if mode == "full" and not worktree_is_clean():
        return
    if mode != "download" and not confirm(confirmation):
        print("Operação cancelada.")
        return

    for index, country in enumerate(countries, start=1):
        print(f"\n===== [{index}/{len(countries)}] {country} =====")
        command = [sys.executable, str(SYNC_SCRIPT), "--country", country, *arguments]
        if mode == "full":
            command.extend(["--git-commit-message", f"Add {country} coin images"])
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
            run([sys.executable, str(CHECK_SCRIPT)], accepted_codes={0, 1})
            continue
        modes = {"2": "full", "3": "download", "4": "api"}
        if choice not in modes:
            print("Opção inválida.")
            continue
        countries = choose_countries()
        if countries:
            process_countries(countries, modes[choice])


if __name__ == "__main__":
    raise SystemExit(main())
