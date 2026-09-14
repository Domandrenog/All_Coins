# Comandos principais

Corre os comandos a partir da raiz deste repositório. O ficheiro `.env` tem de
conter `ALL_COINS_API_KEY`; nunca coloques essa chave na linha de comandos.

## Verificar a API inteira

Mostra quantas moedas ainda usam URLs de `i.ucoin.net`, sem alterar nada.

```bash
python3 scripts/check_ucoin_links_api.py
```

## Verificar um país na API

Mostra apenas as moedas de um país que ainda apontam para `i.ucoin.net`, sem
alterar nada.

```bash
python3 scripts/check_ucoin_links_api.py --country "Nova Zelândia"
```

## Simular a troca de URLs para imagens já publicadas

Mostra as URLs raw do GitHub que serão usadas, sem descarregar imagens, fazer
commit, push ou alterar a API.

```bash
python3 scripts/sync_coin_images_api.py \
  --country "Nova Zelândia" \
  --country-folder NovaZelandia \
  --api-only \
  --no-git-push
```

## Aplicar a troca de URLs na Base44

Atualiza `image_frente` e `image_verso` na API para os ficheiros já publicados
em `NovaZelandia/frente` e `NovaZelandia/tras`. Não descarrega imagens nem faz
operações Git.

```bash
python3 scripts/sync_coin_images_api.py \
  --country "Nova Zelândia" \
  --country-folder NovaZelandia \
  --api-only \
  --apply \
  --no-git-push
```

## Validar depois da atualização

Confirma que já não há moedas da Nova Zelândia a apontar para `i.ucoin.net`.

```bash
python3 scripts/check_ucoin_links_api.py --country "Nova Zelândia"
```

O resultado esperado termina com `coins_with_ucoin=0` e a mensagem `OK`.

## Descarregar imagens e preparar links locais para outro país

Usa este comando quando as imagens ainda não foram recolhidas. Descarrega as
imagens, atualiza os ficheiros de links locais, mas não altera a API nem faz
commit/push.

```bash
python3 scripts/sync_coin_images_api.py \
  --country "Nome exato na API" \
  --country-folder NomeDaPasta \
  --download-only \
  --no-git-push
```

Depois publica manualmente os ficheiros com `git.exe push` em WSL (ou `git push`
fora de WSL), confirma que terminou, e só então usa a simulação e aplicação da
API acima.
