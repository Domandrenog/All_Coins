# All_Coins

Este repositório guarda imagens de moedas por país e atualiza a API `Coin` para deixar de apontar para `i.ucoin.net`, passando a usar URLs raw do GitHub.

## Fluxo

```mermaid
flowchart LR
  A[Escolher país ou moeda] --> B[Consultar Coin API]
  B --> C{Frente e verso são i.ucoin.net?}
  C -- Não --> D[Manter moeda como está]
  C -- Sim --> E[Gerar slug e URLs raw]
  E --> F[Descarregar imagens]
  F --> G[Guardar em Pais/frente e Pais/tras]
  G --> H[Atualizar links.txt e links-ucoin.txt]
  H --> I[git add, commit e push]
  I --> J[Atualizar image_frente e image_verso na API]
  J --> K[Validar API e raw links]
```

## Preparação

1. Coloca a API key no ficheiro local `.env`:

```env
ALL_COINS_API_KEY=...
```

2. Confirma que `.env` continua ignorado pelo Git:

```bash
git check-ignore -v .env
```

3. Se precisares de instalar dependências de download:

```bash
python3 -m pip install --break-system-packages playwright
python3 -m playwright install chromium
```

Também funciona com `chromium`, `chromium-browser`, `google-chrome` ou `google-chrome-stable` já instalados no sistema.

## Verificar Pendências

Antes de processar países novos, vê se ainda há alguma moeda na API com links uCoin:

```bash
python3 check_ucoin_links_api.py
```

Resultado esperado quando está tudo migrado:

```text
countries_with_ucoin=0
coins_with_ucoin=0
OK: nenhuma moeda ainda aponta para i.ucoin.net.
```

Para verificar só um país:

```bash
python3 check_ucoin_links_api.py --country "EUA"
```

## Processar Um País

O fluxo normal para um país é:

```bash
python3 sync_coin_images_api.py --country "Polónia" --download-current --apply --git-commit-message "Add Poland coin images"
```

Isto faz, por ordem:

1. Consulta as moedas do país na API.
2. Salta moedas que não tenham `i.ucoin.net` nos dois lados.
3. Descarrega `image_frente` e `image_verso` atuais.
4. Guarda imagens em `<Pais>/frente` e `<Pais>/tras`.
5. Atualiza `<Pais>/links.txt` com URLs raw do GitHub.
6. Atualiza `<Pais>/links-ucoin.txt` com os URLs originais do uCoin.
7. Faz `git add .`, `git commit` e `git push`.
8. Atualiza `image_frente` e `image_verso` na API.
9. Volta a consultar a API para verificar a atualização.

Os URLs raw ficam neste formato:

```text
https://raw.githubusercontent.com/Domandrenog/All_Coins/main/<Pais>/frente/<slug>.jpg
https://raw.githubusercontent.com/Domandrenog/All_Coins/main/<Pais>/tras/<slug>.jpg
```

## Testar Sem Alterar

Para ver o plano sem descarregar, sem commit e sem atualizar a API:

```bash
python3 sync_coin_images_api.py --country "Polónia" --no-git-push
```

Para descarregar e criar links locais, mas sem atualizar a API nem fazer commit/push:

```bash
python3 sync_coin_images_api.py --country "Polónia" --download-only --no-git-push
```

Este modo é útil para países grandes. Depois de validar os ficheiros locais, faz commit/push e só então atualiza a API.

## Processar Uma Moeda

Quando filtras por `--name`, usa sempre `--years` para não apanhar a moeda errada:

```bash
python3 sync_coin_images_api.py --country "Polónia" --name "1 grosz" --years 2018 --download-current --apply
```

Se precisares de forçar um slug específico:

```bash
python3 sync_coin_images_api.py --country "Polónia" --name "1 grosz" --years 2018 --slug poland-1-grosz-2018 --download-current --apply
```

Se já sabes o ID da moeda:

```bash
python3 sync_coin_images_api.py --coin-id "<Coin_id>" --country-folder Polonia --slug poland-1-grosz-2018 --download-current --apply
```

## Regras Importantes

Moedas sem `i.ucoin.net` nos dois lados ficam como estão por defeito. Isto evita substituir imagens da Base44 ou outros hosts por links raw incompletos.

Para forçar inclusão dessas moedas:

```bash
python3 sync_coin_images_api.py --country "Tailândia" --download-current --apply --include-without-ucoin
```

Se duas moedas gerarem o mesmo nome de ficheiro a partir do URL original, o script acrescenta dados da moeda ao slug para manter ficheiros e links separados.

Por defeito, nomes de países são normalizados para pastas sem acentos e com palavras juntas. Exemplos:

- `Índia` vira `India`
- `África do Sul` vira `AfricaDoSul`

Alguns países têm mapeamentos explícitos quando o nome da API não deve ser usado diretamente ou quando há tradução:

- `Bielorrussia`
- `CoreiaDoSul`
- `EmiradosArabesUnidos`
- `Japao`
- `Malasia`
- `Romenia`
- `Russia`
- `Tailandia`
- `Tunisia`
- `EUA`

## Validar Depois

Depois de processar um país, confirma primeiro a API:

```bash
python3 check_ucoin_links_api.py --country "Polónia"
```

Para uma verificação rápida dos ficheiros locais de um país:

```bash
python3 - <<'PY'
from pathlib import Path

folder = Path('Polonia')
links_path = folder / 'links.txt'
entries = []
current = None

for line in links_path.read_text(encoding='utf-8').splitlines():
    if line and not line.startswith(' '):
        current = line.rstrip(':')
    elif current and line.strip().startswith(('frente:', 'tras:')):
        side, url = line.strip().split(': ', 1)
        entries.append((current, side, url))

print('moedas=', len({slug for slug, _, _ in entries}))
print('links=', len(entries))
print('frente=', len(list((folder / 'frente').glob('*.jpg'))))
print('tras=', len(list((folder / 'tras').glob('*.jpg'))))
PY
```

## Ficheiros Gerados

Cada país processado fica com:

```text
<Pais>/
  links.txt
  links-ucoin.txt
  frente/
    <slug>.jpg
  tras/
    <slug>.jpg
```

`links.txt` guarda os URLs raw usados pela API.

`links-ucoin.txt` guarda os URLs originais do uCoin para referência histórica.

## Troubleshooting

Se um download uCoin falhar, testa o URL isoladamente:

```bash
python3 probe_ucoin_download.py "https://i.ucoin.net/coin/.../imagem.jpg"
```

Para testar com Chromium/Playwright:

```bash
python3 probe_ucoin_download.py "https://i.ucoin.net/coin/.../imagem.jpg" --playwright
```

Um download só conta como sucesso quando:

- HTTP é `2xx`;
- `Content-Type` contém `image`;
- o ficheiro tem conteúdo.

Se o resultado for `403` ou HTML com `Just a moment...`, é bloqueio Cloudflare.

Se o resultado for `404` no Chromium autenticado, o link do uCoin provavelmente está quebrado; deixa essa moeda como está até haver imagem válida.

## Ferramentas Antigas

`download_images.py` ainda existe para recolher imagens a partir de uma página ou ficheiro de input, mas o fluxo principal hoje é `sync_coin_images_api.py`.

Exemplo com URL:

```bash
python3 download_images.py --url "https://track-coin-collection.base44.app/country?continent=Europa&country=Bielorr%C3%BAssia" --output Bielorrussia
```

Exemplo com login manual no Chromium:

```bash
python3 download_images.py --url "https://track-coin-collection.base44.app/country?continent=Europa&country=Bielorr%C3%BAssia" --output Bielorrussia --headful --manual-login
```

Exemplo com ficheiro de links:

```bash
python3 download_images.py --input links.txt --output Bielorrussia
```
