#!/usr/bin/env python3
"""
Recebe um URL de página ou um ficheiro com links/logs, extrai imagens e grava
com o mesmo nome no diretório escolhido.

Exemplos:
    python3 download_images.py --url "https://..." --output Bielorrussia
    python3 download_images.py --input links.txt --output Bielorrussia
    python3 download_images.py --input logs.txt --output Bielorrussia --base-url https://i.ucoin.net
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from html import unescape
from pathlib import Path
from shutil import which
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp", "gif", "bmp", "svg")

FULL_URL_RE = re.compile(
    rf"https?://[^\s\"'<>]+?\.({'|'.join(IMAGE_EXTENSIONS)})(?:\?[^\s\"'<>]*)?",
    re.IGNORECASE,
)

DOMAIN_PATH_RE = re.compile(
    rf"\b([a-z0-9.-]+\.[a-z]{{2,}}/[^\s\"'<>]+?\.({'|'.join(IMAGE_EXTENSIONS)})(?:\?[^\s\"'<>]*)?)",
    re.IGNORECASE,
)

FILENAME_RE = re.compile(
    rf"\b([a-z0-9._-]+\.({'|'.join(IMAGE_EXTENSIONS)}))(?::\d+)?\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrai imagens de um URL ou ficheiro e descarrega para uma pasta."
    )
    parser.add_argument("--url", help="URL da página a inspecionar")
    parser.add_argument("--input", help="Ficheiro com links/logs")
    parser.add_argument("--output", required=True, help="Pasta de destino")
    parser.add_argument(
        "--base-url",
        default="",
        help="Base URL para nomes de ficheiro sem URL completa (ex.: https://i.ucoin.net/)",
    )
    parser.add_argument(
        "--referer",
        default="",
        help="Valor do header Referer para sites que bloqueiam hotlinking",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Timeout de download em segundos (default: 20)",
    )
    parser.add_argument(
        "--chrome-path",
        default="",
        help="Caminho para o Chrome/Chromium a usar com Playwright (opcional)",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Abre browser visível (não headless)",
    )
    parser.add_argument(
        "--manual-login",
        action="store_true",
        help="Espera por login manual no browser antes de recolher URLs",
    )
    parser.add_argument(
        "--user-data-dir",
        default=".pw-profile",
        help="Pasta de perfil persistente do Chromium (default: .pw-profile)",
    )
    parser.add_argument(
        "--links-base-url",
        default="https://raw.githubusercontent.com/Domandrenog/All_Coins/main",
        help="Base URL para gerar links.txt prontos para copiar (default: raw do GitHub)",
    )
    return parser.parse_args()


def resolve_browser_executable(chrome_path: str) -> str | None:
    if chrome_path:
        if Path(chrome_path).exists():
            return chrome_path
        raise RuntimeError(f"Chrome/Chromium não encontrado em: {chrome_path}. Ajusta --chrome-path.")

    candidates = [
        which("chromium"),
        which("chromium-browser"),
        which("google-chrome"),
        which("google-chrome-stable"),
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    return None


def is_ucoin_url(url: str) -> bool:
    return "i.ucoin.net" in url.lower()


def normalize_url(token: str, base_url: str) -> str:
    token = token.strip().strip("\"'")

    if token.startswith(("http://", "https://")):
        return token

    if "/" in token and "." in token.split("/")[0]:
        return "https://" + token

    if base_url:
        return urljoin(base_url.rstrip("/") + "/", token)

    return ""


def extract_image_targets(text: str, base_url: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        url = normalize_url(candidate, base_url)
        if url and is_ucoin_url(url) and url not in seen:
            seen.add(url)
            found.append(url)

    for line in text.splitlines():
        matched_url = False

        for match in FULL_URL_RE.finditer(line):
            add(match.group(0))
            matched_url = True

        for match in DOMAIN_PATH_RE.finditer(line):
            add(match.group(1))
            matched_url = True

        if not matched_url:
            for match in FILENAME_RE.finditer(line):
                add(match.group(1))

    return found


def extract_urls_from_html(html: str, page_url: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        candidate = unescape(candidate).strip().strip('"\'')
        if not candidate or candidate.startswith("data:"):
            return

        absolute = candidate
        if not absolute.startswith(("http://", "https://")):
            absolute = urljoin(page_url, absolute)

        if absolute in seen:
            return

        if is_ucoin_url(absolute) and any(ext in absolute.lower() for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg")):
            seen.add(absolute)
            found.append(absolute)

    for attribute in ("src", "href", "data-src", "content", "poster"):
        for match in re.finditer(rf'{attribute}=["\']([^"\']+)["\']', html, re.IGNORECASE):
            add(match.group(1))

    for match in re.finditer(r'srcset=["\']([^"\']+)["\']', html, re.IGNORECASE):
        for part in match.group(1).split(','):
            add(part.strip().split(' ')[0])

    for match in re.finditer(r'https?://[^\s"\']+?(?:\.jpg|\.jpeg|\.png|\.webp|\.gif|\.bmp|\.svg)(?:\?[^\s"\']*)?', html, re.IGNORECASE):
        add(match.group(0))

    for match in re.finditer(r'https?://[^\s"\']*i\.ucoin\.net[^\s"\']*', html, re.IGNORECASE):
        add(match.group(0))

    return found


def collect_from_url(
    page_url: str,
    chrome_path: str,
    *,
    headless: bool,
    manual_login: bool,
    user_data_dir: str,
) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Playwright não está instalado. Executa: python3 -m pip install playwright") from exc

    executable = resolve_browser_executable(chrome_path)
    if manual_login and headless:
        raise RuntimeError("--manual-login requer --headful para poderes autenticar no Chromium.")
    use_persistent_profile = bool(user_data_dir)

    if executable:
        print(f"Browser em uso: {executable}")
    else:
        print("Browser em uso: bundle do Playwright")

    urls: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        candidate = candidate.strip().strip('"\'')
        if not candidate or candidate.startswith("data:"):
            return

        absolute = candidate
        if not absolute.startswith(("http://", "https://")):
            absolute = urljoin(page_url, absolute)

        if is_ucoin_url(absolute) and absolute not in seen:
            seen.add(absolute)
            urls.append(absolute)

    def add_many(candidates: list[str]) -> None:
        for candidate in candidates:
            add(candidate)

    def auto_scroll(page) -> None:
        page.evaluate(
            """
            async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0;
                    const distance = 700;
                    const timer = setInterval(() => {
                        const scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if (totalHeight >= scrollHeight) {
                            clearInterval(timer);
                            window.scrollTo(0, 0);
                            resolve();
                        }
                    }, 250);
                });
            }
            """
        )

    def attach_network_hooks(page) -> None:
        page.on("request", lambda request: add(request.url) if is_ucoin_url(request.url) else None)
        page.on("response", lambda response: add(response.url) if is_ucoin_url(response.url) else None)

    def collect_from_page(page) -> None:
        attach_network_hooks(page)

        page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        if manual_login:
            print("Faz login no Chromium e carrega ENTER aqui no terminal para continuar...")
            try:
                input()
            except EOFError:
                print("Sem stdin interativo; a continuar sem ENTER.")

            if page.is_closed():
                try:
                    page = page.context.new_page(viewport={"width": 1600, "height": 1200})
                    attach_network_hooks(page)
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        "A janela do browser foi fechada durante o login. Volta a executar e mantém o Chromium aberto."
                    ) from exc

            page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)

        auto_scroll(page)
        page.wait_for_timeout(3000)

        html = page.content()
        add_many(extract_urls_from_html(html, page_url))

        dom_urls = page.evaluate(
            r"""
            () => {
              const urls = [];
              const elements = Array.from(document.querySelectorAll('[src], [href], [data-src], [poster], [style], img, source, video, audio, link[rel="preload"]'));
              for (const element of elements) {
                for (const attr of ['src', 'href', 'data-src', 'poster']) {
                  const value = element.getAttribute(attr);
                  if (value) urls.push(value);
                }
                const srcset = element.getAttribute('srcset');
                if (srcset) {
                  for (const part of srcset.split(',')) urls.push(part.trim().split(' ')[0]);
                }
                const style = element.getAttribute('style');
                if (style) {
                  const matches = style.match(/url\(([^)]+)\)/g) || [];
                  for (const match of matches) {
                    const cleaned = match.replace(/^url\(['"]?/, '').replace(/['"]?\)$/, '');
                    urls.push(cleaned);
                  }
                }
              }
              return urls;
            }
            """
        )
        add_many([str(url) for url in dom_urls])

        raw_iucoin_urls = re.findall(r'https?://[^\s"\']*i\.ucoin\.net[^\s"\']*', html, re.IGNORECASE)
        add_many(raw_iucoin_urls)

    with sync_playwright() as p:
        launch_options = {
            "headless": headless,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if executable:
            launch_options["executable_path"] = executable

        if use_persistent_profile:
            profile_dir = str(Path(user_data_dir).resolve())
            context = p.chromium.launch_persistent_context(
                profile_dir,
                **launch_options,
                viewport={"width": 1600, "height": 1200},
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                collect_from_page(page)
                return urls
            finally:
                context.close()

        browser = p.chromium.launch(**launch_options)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1200})
            collect_from_page(page)
            return urls
        finally:
            browser.close()


def safe_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name
    return name or "image"


def side_folder_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    if re.search(r"-1s(?:/|$)", path):
        return "frente"
    if re.search(r"-2s(?:/|$)", path):
        return "tras"
    return "outras"


def target_path_for_url(url: str, out_dir: Path) -> Path:
    filename = safe_name_from_url(url)
    side_dir = out_dir / side_folder_from_url(url)
    side_dir.mkdir(parents=True, exist_ok=True)
    return side_dir / filename


def write_grouped_links_file(out_dir: Path, rel_paths: list[Path], links_base_url: str, file_name: str = "links.txt") -> None:
    base = links_base_url.rstrip("/")
    grouped: dict[str, dict[str, str]] = {}

    for rel_path in rel_paths:
        parts = rel_path.parts
        if len(parts) < 3:
            continue

        folder = parts[-2].lower()
        filename = parts[-1]
        coin_name = Path(filename).stem

        encoded_parts = [quote(part, safe="") for part in parts]
        url = f"{base}/{'/'.join(encoded_parts)}"

        entry = grouped.setdefault(coin_name, {})
        entry[folder] = url

    lines: list[str] = []
    for coin_name in sorted(grouped.keys()):
        lines.append(f"{coin_name}:")
        coin_links = grouped[coin_name]
        if "frente" in coin_links:
            lines.append(f"  frente: {coin_links['frente']}")
        if "tras" in coin_links:
            lines.append(f"  tras: {coin_links['tras']}")
        if "outras" in coin_links:
            lines.append(f"  outras: {coin_links['outras']}")
        lines.append("")

    target = out_dir / file_name
    content = "\n".join(lines).rstrip() + "\n" if lines else ""
    target.write_text(content, encoding="utf-8")


def download_with_curl(url: str, target: Path, timeout: int, referer: str) -> tuple[bool, str]:
    curl_bin = which("curl")
    if not curl_bin:
        return False, "curl não encontrado no sistema"

    cmd = [
        curl_bin,
        "-fL",
        "--connect-timeout",
        str(timeout),
        "--max-time",
        str(max(timeout * 3, timeout + 10)),
        "-A",
        "Mozilla/5.0",
        "-H",
        "Accept: image/*,*/*;q=0.8",
        "-o",
        str(target),
        url,
    ]
    if referer:
        cmd[1:1] = ["-e", referer]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        details = (proc.stderr or proc.stdout or "erro desconhecido").strip().splitlines()
        return False, f"[ERRO] {url} -> curl falhou ({details[-1] if details else 'sem detalhes'})"

    if not target.exists() or target.stat().st_size == 0:
        return False, f"[ERRO] {url} -> ficheiro vazio após curl"

    return True, f"[OK] {url} -> {target.name} ({target.stat().st_size} bytes)"


def download(url: str, out_dir: Path, timeout: int, referer: str) -> tuple[bool, str]:
    target = target_path_for_url(url, out_dir)
    target_rel = target.relative_to(out_dir)

    if is_ucoin_url(url):
        ok, message = download_with_curl(url, target, timeout, referer)
        if ok:
            return ok, message.replace(f"-> {target.name}", f"-> {target_rel}")

    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/*,*/*;q=0.8",
            **({"Referer": referer} if referer else {}),
        },
    )

    try:
        with urlopen(req, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if content_type and "image" not in content_type.lower():
                return False, f"[SKIP] {url} -> conteúdo não parece imagem ({content_type})"

            data = response.read()
            target.write_bytes(data)
            return True, f"[OK] {url} -> {target_rel} ({len(data)} bytes)"
    except Exception as exc:  # noqa: BLE001
        return False, f"[ERRO] {url} -> {exc}"


def main() -> int:
    args = parse_args()

    if not args.url and not args.input:
        print("Tens de indicar --url ou --input.")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.url:
        urls = collect_from_url(
            args.url,
            args.chrome_path,
            headless=not args.headful,
            manual_login=args.manual_login,
            user_data_dir=args.user_data_dir,
        )
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Ficheiro de input não encontrado: {input_path}")
            return 1
        raw_text = input_path.read_text(encoding="utf-8", errors="ignore")
        urls = extract_image_targets(raw_text, args.base_url)

    if not urls:
        print("Nenhuma imagem encontrada no input.")
        return 1

    print(f"Imagens encontradas: {len(urls)}")

    referer = args.referer or (args.url or "")

    ok = 0
    fail = 0
    downloaded_rel_paths: list[Path] = []
    for url in urls:
        success, message = download(url, output_dir, args.timeout, referer)
        print(message)
        if success:
            ok += 1
            target = target_path_for_url(url, output_dir)
            rel_target = target.relative_to(output_dir.parent)
            downloaded_rel_paths.append(rel_target)
        else:
            fail += 1

    if ok > 0:
        write_grouped_links_file(output_dir, downloaded_rel_paths, args.links_base_url, "links.txt")
        print("Ficheiro de links gerado na raiz: links.txt (agrupado por moeda)")

    print(f"\nResumo: {ok} sucesso(s), {fail} falha(s).")
    return 0 if ok > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
