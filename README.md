# All_Coins – download de imagens i.ucoin.net

## Como ir buscar as imagens (rápido)

### Opção 0: Atualizar URLs na API para o raw do GitHub

O script `sync_coin_images_api.py` procura moedas na API e atualiza `image_frente`/`image_verso` para apontarem para o raw do GitHub.

Os URLs são gerados neste formato:

- `https://raw.githubusercontent.com/Domandrenog/All_Coins/main/<Pais>/frente/<slug>.jpg`
- `https://raw.githubusercontent.com/Domandrenog/All_Coins/main/<Pais>/tras/<slug>.jpg`

Além de atualizar `links.txt` com os URLs raw, o script também mantém `links-ucoin.txt` na raiz do país com os URLs originais do `i.ucoin.net`, quando a moeda ainda vem da API com esses links.

1. Define a API key fora do repo:
  - `export ALL_COINS_API_KEY="..."`
2. Testa primeiro um país sem alterar a API:
  - `python3 sync_coin_images_api.py --country Polonia`
3. Se quiseres limitar a uma moeda:
  - `python3 sync_coin_images_api.py --country Polonia --name "1 grosz" --years 2018`
4. Quando o resultado estiver certo, aplica:
  - `python3 sync_coin_images_api.py --country Polonia --apply`

Quando usares `--name`, indica sempre `--years`; o script exige esse filtro para evitar atualizar a moeda errada quando o mesmo país tem várias moedas com o mesmo nome.

Em execuções reais (`--apply` ou `--download-only`), o script faz automaticamente:

- `git add .`
- `git commit -m "Update coin image assets"`
- `git push`

Isto garante que as imagens ficam disponíveis no GitHub antes da API apontar para os URLs raw. Para desligar esse comportamento:

- `python3 sync_coin_images_api.py --country Polonia --apply --no-git-push`

Para escolher a mensagem do commit automático:

- `python3 sync_coin_images_api.py --country Polonia --apply --git-commit-message "Add Poland coin images"`

Se precisares de forçar o slug de uma moeda específica:

- `python3 sync_coin_images_api.py --country Polonia --name "1 grosz" --years 2018 --slug poland-1-grosz-2018`

Para países com acentos ou nomes compostos, o script infere pastas sem acentos, por exemplo `EmiradosArabesUnidos`, `Japao`, `Malasia`, `Singapura` e `Taiwan`.

Se a moeda não for encontrada pelos filtros, indica o ID diretamente:

- `python3 sync_coin_images_api.py --coin-id "<Coin_id>" --country-folder Polonia --slug poland-1-grosz-2018`

Para descarregar as imagens atuais da API antes de trocar os links:

- `python3 sync_coin_images_api.py --country Polonia --name "1 grosz" --years 2018 --download-current --apply`

### Opção 1: Gerar localmente com o script

1. Corre o script:
  - `python3 download_images.py --url "https://track-coin-collection.base44.app/country?continent=Europa&country=Bielorr%C3%BAssia" --output Bielorrussia`
2. As imagens ficam em:
  - `Bielorrussia/frente`
  - `Bielorrussia/tras`

### Opção 2: Buscar diretamente do GitHub (raw)

Exemplo direto:

- https://raw.githubusercontent.com/Domandrenog/All_Coins/main/Bielorrussia/1kopek.png

Este projeto usa o `download_images.py` para recolher e guardar imagens de moedas, mantendo o nome original dos ficheiros.

## Objetivo

1. Abrir uma página (ex.: país Bielorrússia).
2. Recolher apenas links que contenham `i.ucoin.net`.
3. Descarregar as imagens para uma pasta de destino (ex.: `Bielorrussia`).
4. Manter o nome do ficheiro vindo do URL.

## Diagnóstico de downloads uCoin

Para descobrir se uma imagem `i.ucoin.net` pode ser descarregada neste ambiente, usa o probe:

- `python3 probe_ucoin_download.py "https://i.ucoin.net/coin/.../imagem.jpg"`

O script testa `urllib`, `curl`, headers de browser e referers derivados do nome da imagem. Para testar também via Chromium/Playwright:

- `python3 probe_ucoin_download.py "https://i.ucoin.net/coin/.../imagem.jpg" --playwright`

Um download só é tratado como sucesso quando o HTTP é `2xx`, o `Content-Type` contém `image` e o ficheiro tem conteúdo. Se o resultado mostrar `403` com `Just a moment...`, o servidor devolveu a página de proteção Cloudflare em vez da imagem.

## Lógica do script

### 1) Entrada
O script aceita dois modos:
- `--url`: abre uma página com Playwright e tenta descobrir URLs de imagem.
- `--input`: lê um ficheiro de texto/logs e extrai URLs diretamente.

### 2) Navegação da página (`--url`)
Com Playwright, o script:
- lança Chromium/Chrome em modo headless;
- monitoriza requests e responses de rede;
- espera carregamento inicial e faz scroll automático;
- extrai links de:
  - atributos HTML (`src`, `href`, `data-src`, `poster`, `srcset`),
  - estilos inline com `url(...)`,
  - regex no HTML bruto.

### 3) Filtro de domínio
Só entram no resultado URLs que contenham `i.ucoin.net`.

### 4) Download
Para cada URL filtrado:
- calcula o nome do ficheiro a partir do path do URL;
- cria subpastas por lado dentro de `--output`:
  - `frente` para URLs com `-1s`
  - `tras` para URLs com `-2s`
  - `outras` para casos sem lado identificado
- grava com o mesmo nome original dentro da subpasta correta;
- valida `Content-Type` para confirmar que é imagem.

Para `i.ucoin.net`, o script usa `curl` no Linux/WSL, porque esse domínio pode devolver `403` quando o pedido é feito por `urllib` (fingerprint/TLS de cliente).

### 5) Resultado
No fim, imprime:
- total de imagens encontradas;
- sucesso/erro por URL;
- resumo final de downloads.

Além disso, são gerados ficheiros de links na raiz de `Bielorrussia` (fora de `frente`/`tras`):

- `links.txt` (agrupado por moeda, com `frente` e `tras`)

Base por defeito:

- `https://raw.githubusercontent.com/Domandrenog/All_Coins/main`

Se quiseres outra base, usa:

- `--links-base-url "https://raw.githubusercontent.com/<user>/<repo>/<branch>"`

## Dependências

- Python 3
- Playwright para Python
- Browser Chromium/Chrome disponível no Linux/WSL

Instalação típica:

- `python3 -m pip install --break-system-packages playwright`
- `python3 -m playwright install chromium`

> Nota: em algumas distribuições recentes, o `playwright install chromium` pode não suportar a versão do Ubuntu. Nesse caso, usar `chromium` do sistema (apt/snap) também funciona, desde que esteja no `PATH`.

## Execução

Exemplo com URL:

- `python3 download_images.py --url "https://track-coin-collection.base44.app/country?continent=Europa&country=Bielorr%C3%BAssia" --output Bielorrussia`

Exemplo com login manual no Chromium (recomendado quando a página redireciona para login):

- `python3 download_images.py --url "https://track-coin-collection.base44.app/country?continent=Europa&country=Bielorr%C3%BAssia" --output Bielorrussia --headful --manual-login`

Se precisares de forçar um binário específico:

- `python3 download_images.py --url "..." --output Bielorrussia --headful --manual-login --chrome-path /snap/bin/chromium`

## Login persistente

O script já usa, por defeito, um perfil persistente em `.pw-profile` (opção `--user-data-dir`).

Fluxo recomendado:

1. Primeira execução com login manual:
  - `python3 download_images.py --url "https://track-coin-collection.base44.app/country?continent=Europa&country=Bielorr%C3%BAssia" --output Bielorrussia --headful --manual-login`
2. Execuções seguintes (reutiliza sessão guardada):
  - `python3 download_images.py --url "https://track-coin-collection.base44.app/country?continent=Europa&country=Bielorr%C3%BAssia" --output Bielorrussia`

Se quiseres outro perfil/sessão, indica outra pasta:

- `python3 download_images.py --url "..." --output Bielorrussia --user-data-dir .pw-profile-alt`

Exemplo com ficheiro de links:

- `python3 download_images.py --input links.txt --output Bielorrussia`

## Nota importante (estado atual)

Atualmente, essa URL redireciona para login (`/login`) no ambiente testado. Quando isso acontece, o script não encontra links `i.ucoin.net` nessa sessão pública.

Se houver autenticação válida (sessão/cookies) ou um endpoint público com os links, o mesmo fluxo passa a descarregar normalmente.
