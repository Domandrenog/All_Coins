#!/usr/bin/env python3
"""Testa estratégias de download para imagens do i.ucoin.net."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


@dataclass
class ProbeResult:
    name: str
    ok: bool
    status: str
    detail: str
    output: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experimenta várias formas de descarregar uma imagem i.ucoin.net e reporta o resultado."
    )
    parser.add_argument("url", help="URL da imagem i.ucoin.net a testar.")
    parser.add_argument("--referer", help="Referer explícito a testar, ex.: página da moeda no uCoin.")
    parser.add_argument("--output-dir", default="ucoin_probe_output", help="Pasta para guardar downloads bem-sucedidos.")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout base em segundos.")
    parser.add_argument("--keep-failed", action="store_true", help="Mantém ficheiros parciais de tentativas falhadas.")
    parser.add_argument("--playwright", action="store_true", help="Também testa via Chromium/Playwright, se estiver instalado.")
    parser.add_argument("--headful", action="store_true", help="Abre Chromium visível no probe Playwright.")
    parser.add_argument("--interactive-login", action="store_true", help="Abre Chromium visível e espera confirmação antes de tentar a imagem.")
    parser.add_argument("--user-data-dir", default=".pw-profile", help="Perfil persistente para o probe Playwright.")
    return parser.parse_args()


def image_filename(url: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    return name or "ucoin-image.jpg"


def derived_referers(url: str) -> list[str]:
    stem = Path(image_filename(url)).stem
    referers = []
    if stem:
        referers.append(f"https://en.ucoin.net/coin/{stem}/")

        normalized = stem.replace("_", "-")
        if normalized != stem:
            referers.append(f"https://en.ucoin.net/coin/{normalized}/")

        without_year = re.sub(r"-\d{4}$", "", normalized)
        if without_year and without_year != normalized:
            referers.append(f"https://en.ucoin.net/coin/{without_year}/")

    return list(dict.fromkeys(referers))


def browser_headers(referer: str = "") -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,pt;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def urllib_probe(name: str, url: str, output: Path, headers: dict[str, str], timeout: int) -> ProbeResult:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(body)
            ok = output.stat().st_size > 0 and "image" in content_type.lower()
            return ProbeResult(name, ok, str(response.status), f"{content_type}; {len(body)} bytes", output)
    except HTTPError as exc:
        body = exc.read(300).decode("utf-8", errors="replace").replace("\n", " ")
        return ProbeResult(name, False, str(exc.code), body)
    except URLError as exc:
        return ProbeResult(name, False, "url-error", str(exc.reason))


def curl_probe(name: str, url: str, output: Path, headers: dict[str, str], timeout: int) -> ProbeResult:
    curl_bin = which("curl")
    if not curl_bin:
        return ProbeResult(name, False, "missing", "curl não encontrado")

    output.parent.mkdir(parents=True, exist_ok=True)
    header_args: list[str] = []
    for key, value in headers.items():
        if key.lower() == "user-agent":
            header_args.extend(["-A", value])
        elif key.lower() == "referer":
            header_args.extend(["-e", value])
        else:
            header_args.extend(["-H", f"{key}: {value}"])

    proc = subprocess.run(
        [
            curl_bin,
            "-L",
            "--connect-timeout",
            str(timeout),
            "--max-time",
            str(timeout * 3),
            "--compressed",
            "-w",
            "http=%{http_code} content_type=%{content_type} size=%{size_download} url=%{url_effective}",
            "-o",
            str(output),
            *header_args,
            url,
        ],
        capture_output=True,
        text=True,
    )
    metadata = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip().splitlines()
    status_match = re.search(r"http=(\d+)", metadata)
    status = status_match.group(1) if status_match else f"exit-{proc.returncode}"
    content_type_match = re.search(r"content_type=([^ ]+)", metadata)
    content_type = content_type_match.group(1) if content_type_match else ""
    ok = (
        proc.returncode == 0
        and status.isdigit()
        and 200 <= int(status) < 300
        and "image" in content_type.lower()
        and output.exists()
        and output.stat().st_size > 0
    )
    detail = metadata or (stderr[-1] if stderr else "sem detalhe")
    return ProbeResult(name, ok, status, detail, output if ok else None)


def playwright_probe(
    name: str,
    url: str,
    output: Path,
    headful: bool,
    user_data_dir: str,
    timeout: int,
    login_url: str = "",
    interactive_login: bool = False,
) -> ProbeResult:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(name, False, "missing", f"Playwright indisponível: {exc}")

    output.parent.mkdir(parents=True, exist_ok=True)
    executable = which("chromium") or which("chromium-browser") or which("google-chrome") or which("google-chrome-stable")
    launch_options = {"executable_path": executable} if executable else {}

    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir,
                headless=not headful,
                accept_downloads=True,
                ignore_https_errors=True,
                **launch_options,
            )
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(name, False, "browser-error", str(exc).splitlines()[0])

        page = context.new_page()
        try:
            if interactive_login:
                first_url = login_url or "https://en.ucoin.net/"
                try:
                    page.goto(first_url, wait_until="domcontentloaded", timeout=timeout * 1000)
                except Exception as exc:  # noqa: BLE001
                    print(f"\nNão consegui abrir automaticamente {first_url}: {str(exc).splitlines()[0]}")
                print("\nChromium aberto. Faz login/passa Cloudflare nessa janela se necessário.")
                print(f"Se a página não abriu, navega manualmente para: {first_url}")
                input("Quando estiver pronto, prime Enter aqui para tentar descarregar a imagem...")

            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            if response is None:
                return ProbeResult(name, False, "no-response", "page.goto não devolveu response")

            status = str(response.status)
            content_type = response.headers.get("content-type", "")
            body = response.body()
            if 200 <= response.status < 300 and "image" in content_type.lower() and body:
                output.write_bytes(body)
                return ProbeResult(name, True, status, f"{content_type}; {len(body)} bytes", output)

            preview = body[:300].decode("utf-8", errors="replace").replace("\n", " ") if body else "sem body"
            return ProbeResult(name, False, status, f"{content_type}; {preview}")
        finally:
            context.close()


def print_result(result: ProbeResult) -> None:
    marker = "OK" if result.ok else "FAIL"
    print(f"[{marker}] {result.name}")
    print(f"  status: {result.status}")
    print(f"  detail: {result.detail}")
    if result.output:
        print(f"  output: {result.output} ({result.output.stat().st_size} bytes)")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    filename = image_filename(args.url)

    referers = []
    if args.referer:
        referers.append(args.referer)
    referers.extend(derived_referers(args.url))
    referers = list(dict.fromkeys(referers))

    probes: list[tuple[str, dict[str, str], str]] = [
        ("urllib-basic", {"User-Agent": "Mozilla/5.0", "Accept": "image/*,*/*;q=0.8"}, "urllib"),
        ("urllib-browser", browser_headers(), "urllib"),
        ("curl-basic", {"User-Agent": "Mozilla/5.0", "Accept": "image/*,*/*;q=0.8"}, "curl"),
        ("curl-browser", browser_headers(), "curl"),
    ]
    for index, referer in enumerate(referers, start=1):
        probes.append((f"urllib-referer-{index}", browser_headers(referer), "urllib"))
        probes.append((f"curl-referer-{index}", browser_headers(referer), "curl"))

    successful = False
    for name, headers, engine in probes:
        output = output_dir / f"{name}-{filename}"
        if output.exists():
            output.unlink()
        if engine == "urllib":
            result = urllib_probe(name, args.url, output, headers, args.timeout)
        else:
            result = curl_probe(name, args.url, output, headers, args.timeout)

        if not result.ok and output.exists() and not args.keep_failed:
            output.unlink()

        print_result(result)
        successful = successful or result.ok

    if successful:
        print("\nPelo menos uma estratégia funcionou.")
        return 0

    if args.playwright or args.interactive_login:
        output = output_dir / f"playwright-{filename}"
        if output.exists():
            output.unlink()
        login_url = args.referer or (referers[0] if referers else "")
        result = playwright_probe(
            "playwright-browser",
            args.url,
            output,
            args.headful or args.interactive_login,
            args.user_data_dir,
            args.timeout,
            login_url,
            args.interactive_login,
        )
        if not result.ok and output.exists() and not args.keep_failed:
            output.unlink()
        print_result(result)
        if result.ok:
            print("\nO probe via browser funcionou.")
            return 0

    print("\nNenhuma estratégia funcionou. O servidor pode estar a bloquear por sessão, cookie, IP ou proteção anti-hotlink.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())