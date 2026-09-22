#!/usr/bin/env python3
"""Menu simples para preparar imagens e migrar os URLs na Base44."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

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
    "souvenir": "Souvenirs",
}

NOTES_CDP_URL = "http://127.0.0.1:9222"
NUMISTA_START_URL = "https://pt.numista.com/"
NOTES_BROWSER_PROFILE_MARKER = ""
NOTES_BROWSER_PROCESS: subprocess.Popen[bytes] | None = None


def clear_screen() -> None:
    """Limpa o terminal antes de apresentar o próximo ecrã do menu."""
    # ANSI funciona nos terminais suportados pelo Python em Windows, Linux e macOS.
    print("\033[2J\033[H", end="")


def wait_for_continue() -> None:
    """Mantém o resultado visível até o utilizador voltar ao menu."""
    input("\nPrima Enter para voltar ao menu...")


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


def catalog_type_filter(catalog: str) -> str | None:
    """Mantém o fluxo de Souvenirs focado nas prensadas já suportadas."""
    return "pressed" if catalog == "souvenir" else None


def choose_catalog(*, allow_all: bool = False) -> list[str] | None:
    clear_screen()
    print("\n1. Moedas normais\n2. Moedas de coleção\n3. Notas\n4. Souvenirs")
    if allow_all:
        print("5. Todas as categorias")
    print("0. Voltar")
    choice = input("Escolha a categoria: ").strip()
    choices = {"1": "normal", "2": "collection", "3": "notes", "4": "souvenir"}
    if allow_all and choice == "5":
        return list(CATALOG_LABELS)
    if choice == "0":
        return None
    catalog = choices.get(choice)
    if not catalog:
        print("Opção inválida.")
        return None
    return [catalog]


def read_pending_report(catalog: str, record_type: str | None = None) -> dict[str, object] | None:
    _, check_script = scripts_for_catalog(catalog)
    command = catalog_command(check_script, catalog)
    if record_type:
        command.extend(["--type", record_type])
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


def choose_countries(catalog: str, record_type: str | None = None) -> list[str] | None:
    clear_screen()
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

    report = read_pending_report(catalog, record_type)
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


def cdp_json(path: str, *, method: str = "GET") -> object:
    request = Request(f"{NOTES_CDP_URL}{path}", method=method)
    with urlopen(request, timeout=2) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def cdp_is_available() -> bool:
    try:
        cdp_json("/json/version")
        return True
    except (OSError, URLError, ValueError):
        return False


def numista_is_ready() -> bool:
    try:
        targets = cdp_json("/json")
    except (OSError, URLError, ValueError):
        return False
    if not isinstance(targets, list):
        return False
    for target in targets:
        if not isinstance(target, dict):
            continue
        url = str(target.get("url") or "").lower()
        title = str(target.get("title") or "").lower()
        if "numista.com" not in url:
            continue
        if "challenge.php" not in url and "checking connection" not in title:
            return True
    return False


def open_numista_tab() -> None:
    encoded_url = quote(NUMISTA_START_URL, safe="")
    try:
        cdp_json(f"/json/new?{encoded_url}", method="PUT")
    except (OSError, URLError, ValueError) as exc:
        raise RuntimeError("Não foi possível abrir o Numista na sessão Chrome existente.") from exc


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def launch_notes_browser() -> bool:
    """Abre Chrome com CDP quando necessário; devolve True se o lançou."""
    global NOTES_BROWSER_PROCESS, NOTES_BROWSER_PROFILE_MARKER
    if cdp_is_available():
        if not numista_is_ready():
            open_numista_tab()
        return False

    windows_browsers = [
        (
            Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ),
        (
            Path("/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ),
    ]
    powershell = Path("/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe")
    browser = next((candidate for candidate in windows_browsers if candidate[0].exists()), None)
    NOTES_BROWSER_PROFILE_MARKER = f"all-coins-notes-{os.getpid()}"
    if browser is not None and powershell.exists():
        arguments = [
            "--incognito",
            "--remote-debugging-address=0.0.0.0",
            "--remote-debugging-port=9222",
            f"--user-data-dir=C:\\Temp\\{NOTES_BROWSER_PROFILE_MARKER}",
            "--no-first-run",
            "--no-default-browser-check",
            NUMISTA_START_URL,
        ]
        command = (
            f"Start-Process -FilePath {powershell_quote(browser[1])} "
            f"-ArgumentList {','.join(powershell_quote(value) for value in arguments)}"
        )
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-Command", command],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "Não foi possível abrir o Chrome do Windows.")
    else:
        executable = next(
            (shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable") if shutil.which(name)),
            None,
        )
        if executable is None:
            raise RuntimeError("Chrome/Chromium não encontrado para abrir a sessão Numista.")
        NOTES_BROWSER_PROCESS = subprocess.Popen(
            [
                executable,
                "--incognito",
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=9222",
                f"--user-data-dir=/tmp/{NOTES_BROWSER_PROFILE_MARKER}",
                "--no-first-run",
                "--no-default-browser-check",
                NUMISTA_START_URL,
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    for _ in range(60):
        if cdp_is_available():
            return True
        time.sleep(0.25)
    raise RuntimeError("O Chrome abriu, mas a porta CDP 9222 não ficou disponível em 15 segundos.")


def prepare_notes_browser() -> bool:
    launched = launch_notes_browser()
    print("\nA janela do Numista está aberta para os downloads das notas.")
    while not numista_is_ready():
        input(
            "Resolve o Cloudflare nessa janela e, quando aparecer a página normal do Numista, "
            "carrega Enter aqui... "
        )
        if not cdp_is_available():
            raise RuntimeError("A janela Chrome foi fechada antes de concluir o Cloudflare.")
        if not numista_is_ready():
            print("O Numista ainda mostra o desafio. Resolve-o na janela e tenta novamente.")
    print("Numista pronto; a sessão será reutilizada durante o lote.")
    return launched


def close_notes_browser() -> None:
    global NOTES_BROWSER_PROCESS, NOTES_BROWSER_PROFILE_MARKER
    marker = NOTES_BROWSER_PROFILE_MARKER
    if not marker:
        print("A sessão Chrome já existia antes do menu; ficou aberta.")
        return

    windows_powershell = Path("/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe")
    try:
        if windows_powershell.exists():
            escaped_marker = marker.replace("'", "''")
            command = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -match 'chrome|msedge' -and "
                f"$_.CommandLine -like '*{escaped_marker}*' }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }"
            )
            subprocess.run(
                [str(windows_powershell), "-NoProfile", "-Command", command],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=15,
            )
        elif NOTES_BROWSER_PROCESS is not None and NOTES_BROWSER_PROCESS.poll() is None:
            NOTES_BROWSER_PROCESS.terminate()
            try:
                NOTES_BROWSER_PROCESS.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print("A sessão temporária não fechou automaticamente; podes fechar a janela manualmente.")
                return

        for _ in range(20):
            if not cdp_is_available():
                print("Sessão Chrome temporária fechada.")
                return
            time.sleep(0.25)
        print("A sessão temporária ficou aberta; podes fechar a janela manualmente.")
    finally:
        NOTES_BROWSER_PROCESS = None
        NOTES_BROWSER_PROFILE_MARKER = ""


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


def process_countries(
    countries: list[str], mode: str, catalog: str, record_type: str | None = None
) -> None:
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

    browser_launched = False
    try:
        if catalog == "notes" and mode in {"full", "download"}:
            browser_launched = prepare_notes_browser()

        for index, country in enumerate(countries, start=1):
            print(f"\n===== [{index}/{len(countries)}] {country} =====")
            sync_script, _ = scripts_for_catalog(catalog)
            command = catalog_command(sync_script, catalog)
            command.extend(["--country", country, *arguments])
            if record_type:
                command.extend(["--type", record_type])
            if catalog == "notes":
                command.extend(["--cdp-url", NOTES_CDP_URL])
            if mode == "full":
                command.extend(["--git-commit-message", f"Add {country} {catalog} images"])
            if not run(command):
                print(f"Processamento interrompido em {country}. Corrige o erro antes de continuar.")
                return
    except RuntimeError as exc:
        print(f"Não foi possível preparar o browser das notas: {exc}")
        return
    finally:
        if browser_launched:
            close_notes_browser()

    print("\nOperação concluída.")


def print_menu() -> None:
    clear_screen()
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
                    command = catalog_command(check_script, catalog)
                    record_type = catalog_type_filter(catalog)
                    if record_type:
                        command.extend(["--type", record_type])
                    run(command, accepted_codes={0, 1})
                wait_for_continue()
            continue
        modes = {"2": "full", "3": "download", "4": "api"}
        if choice not in modes:
            print("Opção inválida.")
            continue
        catalogs = choose_catalog()
        if not catalogs:
            continue
        catalog = catalogs[0]
        record_type = catalog_type_filter(catalog)
        countries = choose_countries(catalog, record_type)
        if countries:
            process_countries(countries, modes[choice], catalog, record_type)
            wait_for_continue()


if __name__ == "__main__":
    raise SystemExit(main())
