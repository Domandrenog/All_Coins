#!/usr/bin/env python3
"""Menu simples para preparar imagens e migrar os URLs na Base44."""

from __future__ import annotations

import json
from hashlib import sha256
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from scripts.sync_coin_images_api import country_folder, run_git


ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
SYNC_SCRIPT = SCRIPTS / "sync_coin_images_api.py"
CHECK_SCRIPT = SCRIPTS / "check_ucoin_links_api.py"
CATALOG_SYNC_SCRIPT = SCRIPTS / "sync_catalog_images_api.py"
CATALOG_CHECK_SCRIPT = SCRIPTS / "check_catalog_links_api.py"
SOUVENIR_CROPPER_SCRIPT = ROOT / "tools" / "souvenir_cropper.py"
SOUVENIR_PROMOTE_SCRIPT = ROOT / "tools" / "promote_souvenir_crops.py"
SOUVENIR_UPDATE_SCRIPT = ROOT / "tools" / "update_souvenir_manifest_api.py"
SOUVENIR_COUNTRY_DIR = ROOT / "fotos" / "paises" / "America" / "EUA" / "souvenir"

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
    """Processa todos os tipos de Souvenirs suportados pelo catálogo."""
    return None


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


def choose_specific_stage() -> str | None:
    clear_screen()
    print(
        "\n=== Specific stage ===\n"
        "1. Descarregar imagens\n"
        "2. Trocar URLs na Base44\n"
        "0. Voltar"
    )
    choice = input("Escolha uma etapa: ").strip()
    if choice == "0":
        return None
    stages = {"1": "download", "2": "api"}
    stage = stages.get(choice)
    if not stage:
        print("Opção inválida.")
        return None
    return stage


def choose_souvenir_full_action() -> str | None:
    clear_screen()
    print(
        "\n=== Trocar imagens dos Souvenirs ===\n"
        "1. Processar automaticamente\n"
        "2. Recortar manualmente e enviar\n"
        "0. Voltar"
    )
    choice = input("Escolha uma opção: ").strip()
    if choice == "0":
        return None
    actions = {"1": "automatic", "2": "manual"}
    action = actions.get(choice)
    if not action:
        print("Opção inválida.")
        return None
    return action


def launch_souvenir_cropper() -> dict[str, object] | None:
    if not SOUVENIR_CROPPER_SCRIPT.is_file():
        print(f"Recortador não encontrado: {SOUVENIR_CROPPER_SCRIPT}")
        return None
    with TemporaryDirectory(prefix="all-coins-souvenir-") as temporary:
        completion_file = Path(temporary) / "completion.json"
        command = [
            sys.executable,
            str(SOUVENIR_CROPPER_SCRIPT),
            "--completion-file",
            str(completion_file),
        ]
        print("\nA abrir o recortador em http://127.0.0.1:8765 ...")
        print("Recorta e confirma as fotografias; no fim usa ‘Finalizar e enviar’ no browser.")
        print("Os recortes ficam guardados mesmo que canceles com Ctrl+C.")
        process = subprocess.Popen(command, cwd=ROOT)
        time.sleep(1)
        if process.poll() is not None:
            print("O recortador terminou antes de ficar disponível. Confirma se a porta 8765 está livre.")
            return None
        try:
            process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            print("\nRecortador cancelado. Os ficheiros preparados foram mantidos.")
            return None
        if not completion_file.is_file():
            print("Recortador fechado sem pedido de finalização. Os ficheiros preparados foram mantidos.")
            return None
        try:
            request = json.loads(completion_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Não foi possível ler o pedido de finalização: {exc}")
            return None
        if not isinstance(request, dict):
            print("O pedido de finalização devolvido pelo recortador é inválido.")
            return None
        return request


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


def worktree_has_only_souvenir_location_changes(
    location_id: str,
    record_ids: set[str],
) -> bool:
    staging_manifest = ROOT / "recortes_souvenir_teste" / "manifest.json"
    try:
        staging = json.loads(staging_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Não foi possível delimitar os ficheiros concluídos: {exc}")
        return False
    entries = [
        entry
        for record_id, entry in staging.items()
        if str(record_id) in record_ids
        and isinstance(entry, dict)
        and str(entry.get("location_id")) == location_id
    ]
    if len(entries) != len(record_ids):
        print("O manifesto de preparação já não contém todos os IDs concluídos.")
        return False
    root = SOUVENIR_COUNTRY_DIR.relative_to(ROOT)
    allowed = {
        (root / "links-internos.txt").as_posix(),
        (root / "links-externos.txt").as_posix(),
        (root / "recortes-manifest.json").as_posix(),
    }
    allowed.update(
        (root / "frente" / Path(str(entry.get("file") or "")).name).as_posix()
        for entry in entries
    )
    machines = {int(entry.get("machine") or 0) for entry in entries}
    original_prefixes = [
        (root / "original" / f"location-{location_id}-machine-{machine}").as_posix()
        for machine in machines
    ]
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr or "Não foi possível verificar o estado do Git.")
        return False
    changed = [line[3:] for line in result.stdout.splitlines() if len(line) > 3]
    unexpected = [
        item
        for item in changed
        if item not in allowed
        and not any(
            item.startswith(f"{prefix}.")
            and Path(item).suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}
            for prefix in original_prefixes
        )
    ]
    if unexpected:
        print("Existem alterações fora das fotografias concluídas:")
        for item in unexpected:
            print(f"- {item}")
        return False
    return True


def verify_souvenir_raw_images(record_ids: list[str], commit_sha: str) -> bool:
    manifest_path = SOUVENIR_COUNTRY_DIR / "recortes-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Não foi possível verificar o manifesto promovido: {exc}")
        return False
    entries = [
        manifest[record_id]
        for record_id in record_ids
        if isinstance(manifest.get(record_id), dict)
    ]
    if len(entries) != len(record_ids):
        print("O manifesto promovido não contém todos os IDs concluídos.")
        return False
    print(f"\nA verificar {len(entries)} imagens publicadas no GitHub raw...")
    for index, entry in enumerate(entries, 1):
        relative = str(entry.get("front_file") or "")
        url = str(entry.get("internal_front") or "")
        local = SOUVENIR_COUNTRY_DIR / relative
        if not local.is_file() or not url.startswith("https://raw.githubusercontent.com/"):
            print(f"Imagem promovida inválida: {relative or url}")
            return False
        expected = sha256(local.read_bytes()).hexdigest()
        separator = "&" if "?" in url else "?"
        verified = False
        for attempt in range(1, 6):
            try:
                request = Request(
                    f"{url}{separator}commit={quote(commit_sha)}",
                    headers={"Cache-Control": "no-cache", "User-Agent": "All-Coins/1.0"},
                )
                with urlopen(request, timeout=30) as response:
                    actual = sha256(response.read()).hexdigest()
                if actual == expected:
                    verified = True
                    break
            except (OSError, URLError):
                pass
            if attempt < 5:
                time.sleep(2)
        if not verified:
            print(f"A imagem publicada ainda não corresponde ao ficheiro local: {url}")
            return False
        print(f"✓ [{index}/{len(entries)}] {Path(relative).name}")
    return True


def finalize_manual_souvenirs(request: dict[str, object]) -> bool:
    location_id = str(request.get("location_id") or "")
    location_name = str(request.get("location_name") or f"location {location_id}")
    raw_record_ids = request.get("record_ids")
    record_ids = (
        list(dict.fromkeys(str(record_id) for record_id in raw_record_ids if record_id))
        if isinstance(raw_record_ids, list)
        else []
    )
    if not location_id or not record_ids:
        print("O recortador não indicou fotografias concluídas para enviar.")
        return False
    coin_word = "moeda" if len(record_ids) == 1 else "moedas"
    print(
        f"\n===== Enviar Souvenirs concluídos: {location_name} "
        f"({len(record_ids)} {coin_word}) ====="
    )
    selected_ids = set(record_ids)
    if not worktree_has_only_souvenir_location_changes(location_id, selected_ids):
        print("Os recortes continuam guardados e podem ser finalizados depois.")
        return False
    record_arguments = [
        argument
        for record_id in record_ids
        for argument in ("--record-id", record_id)
    ]
    base_command = [
        sys.executable,
        str(SOUVENIR_PROMOTE_SCRIPT),
        "--location-id",
        location_id,
        *record_arguments,
        "--replace-existing",
    ]
    if not run(base_command):
        print("A validação falhou; nada foi publicado nem alterado na Base44.")
        return False
    if not run([*base_command, "--apply"]):
        print("A promoção falhou; a Base44 não foi alterada.")
        return False
    if not worktree_has_only_souvenir_location_changes(location_id, selected_ids):
        print("A promoção criou alterações fora das fotografias concluídas; publicação interrompida.")
        return False
    try:
        status = run_git(["status", "--porcelain"])
        if status:
            relative = SOUVENIR_COUNTRY_DIR.relative_to(ROOT).as_posix()
            print(f"\nGit: add {relative}")
            run_git(["add", "--", relative])
            message = f"Add {location_name} completed souvenir images"
            print(f"Git: commit -m {message!r}")
            run_git(["commit", "-m", message])
        else:
            print("Git: as fotografias concluídas já estavam guardadas num commit.")
        print("Git: push")
        run_git(["push"])
        local_sha = run_git(["rev-parse", "HEAD"]).strip()
        remote_line = run_git(["ls-remote", "--exit-code", "origin", "refs/heads/main"])
        remote_sha = remote_line.split()[0] if remote_line.split() else ""
    except RuntimeError as exc:
        print(f"Falha ao publicar: {exc}")
        print("A Base44 não foi alterada; podes repetir o envio depois.")
        return False
    if remote_sha != local_sha:
        print(f"O main remoto ({remote_sha or 'desconhecido'}) não corresponde ao commit local ({local_sha}).")
        print("A Base44 não foi alterada.")
        return False
    print(f"Git: publicação confirmada em {local_sha[:12]}.")
    if not verify_souvenir_raw_images(record_ids, local_sha):
        print("A Base44 não foi alterada; repete o envio quando os ficheiros estiverem disponíveis.")
        return False
    update_command = [
        sys.executable,
        str(SOUVENIR_UPDATE_SCRIPT),
        "--location-id",
        location_id,
        *record_arguments,
    ]
    if not run(update_command):
        print("A pré-verificação da Base44 falhou; nenhuma atualização foi enviada.")
        return False
    if not run([*update_command, "--apply"]):
        print("A atualização da Base44 falhou. Consulta o resultado acima antes de repetir.")
        return False
    verb = "foi publicada e verificada" if len(record_ids) == 1 else "foram publicadas e verificadas"
    print(
        f"\nEnvio concluído: {len(record_ids)} {coin_word} de {location_name} "
        f"{verb} na Base44."
    )
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
        "3. Specific stage\n"
        "4. Sair"
    )


def main() -> int:
    while True:
        print_menu()
        choice = input("Escolha uma opção: ").strip()
        if choice in {"0", "4"}:
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
        if choice == "2":
            mode = "full"
        elif choice == "3":
            mode = choose_specific_stage()
            if mode is None:
                continue
        else:
            print("Opção inválida.")
            continue
        catalogs = choose_catalog()
        if not catalogs:
            continue
        catalog = catalogs[0]
        record_type = catalog_type_filter(catalog)
        if catalog == "souvenir" and mode == "full":
            souvenir_action = choose_souvenir_full_action()
            if souvenir_action is None:
                continue
            if souvenir_action == "manual":
                completion = launch_souvenir_cropper()
                if completion is not None:
                    finalize_manual_souvenirs(completion)
                wait_for_continue()
                continue
        countries = choose_countries(catalog, record_type)
        if countries:
            process_countries(countries, mode, catalog, record_type)
            wait_for_continue()


if __name__ == "__main__":
    raise SystemExit(main())
