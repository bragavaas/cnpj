# Instruções de operação

Guia rápido para subir o ambiente, carregar os dados e consultar a API. Para entender o dataset
em si (o que cada tabela significa), veja o `README.md`. Para o histórico de decisões de
implementação da API, veja `TASKS_DOCKER_API.md`.

## 1. Subir o banco

```
cp .env.example .env   # ajuste se quiser, os valores padrão já funcionam
docker compose up -d db
```

Espere o container ficar `healthy` (`docker compose ps`).

## 2. Rodar o ETL

```
docker compose run --rm etl
```

Por padrão (`.env.example`) roda em **modo de teste** (`ETL_TEST_MODE=true`): baixa 1 arquivo por
categoria fracionada e insere só as primeiras `ETL_MAX_ROWS` linhas de cada um. Útil para validar
o fluxo em minutos.

Para a carga **completa** (todos os arquivos, todas as linhas — dados reais da Receita Federal),
defina `ETL_TEST_MODE=false` no `.env` antes de rodar o comando acima.

### Recursos necessários para a carga completa

- **Disco**: dezenas de GB (arquivos `.zip` baixados + `.csv` extraídos + o próprio Postgres).
  Confirme espaço livre antes de rodar.
- **Memória do Docker Desktop**: os arquivos de `empresa`/`estabelecimento`/`socios` são lidos em
  pedaços de até 2.000.000 de linhas por vez (não o arquivo inteiro de uma vez), mas alguns
  arquivos individuais já vêm com dezenas de milhões de linhas. Recomenda-se pelo menos **8 GB**
  alocados ao Docker Desktop (Settings → Resources → Memory) para a carga completa rodar com
  folga, especialmente com `db`/`api`/outros containers rodando ao mesmo tempo.
  - **Achado real**: uma carga completa já travou silenciosamente (sem traceback no log) exatamente
    ao processar o primeiro arquivo de `empresa` (2,2 GB / 28 milhões de linhas) rodando com só
    7,44 GiB disponíveis no Docker Desktop — sintoma clássico de OOM kill (processo morto por falta
    de memória não deixa stack trace). O loop de leitura de `empresa` e `socios` foi corrigido para
    ler em pedaços (mesmo padrão que `estabelecimento` já usava), mas memória generosa ainda ajuda
    a carga ir mais rápido e com menos risco em geral.
- Rodar em background e acompanhar o progresso com `docker compose logs -f etl` (ou, se rodou via
  `run --rm`, `docker logs -f <nome-do-container-etl>` — pegue o nome com `docker ps`).

## 3. Subir a API

```
docker compose up -d api
```

- API em `http://localhost:3000`
- Swagger (documentação interativa) em `http://localhost:3000/docs`

## 4. Consultando a API

```
# Healthcheck (inclui teste de conexão com o banco)
curl http://localhost:3000/health

# Consulta por CNPJ (8 dígitos = raiz/matriz, 14 = estabelecimento específico)
curl http://localhost:3000/cnpj/11222333
curl http://localhost:3000/cnpj/11222333000181
curl "http://localhost:3000/cnpj/11222333?all=true"   # todos os estabelecimentos da raiz

# Busca paginada por nome/UF/município/situação/CNAE
curl "http://localhost:3000/empresas/search?razao_social=exemplo&uf=RJ&limit=10"
curl "http://localhost:3000/empresas/search?municipio=Rio%20de%20Janeiro&cnae=8630503"
```

Sem autenticação por padrão — não exponha além de localhost/rede Docker sem adicionar
autenticação antes.

## 5. Troubleshooting

- **`relation "empresa" does not exist` (ou `estabelecimento`/`socios`/etc.) → 500 nos
  endpoints**: o ETL ainda não terminou de popular aquela tabela (cada tabela grande é recriada do
  zero — `DROP TABLE` + `INSERT` — no início do respectivo bloco do script). Verifique o progresso
  com `docker logs <container-etl>` ou `data/etl_full_load.log`. Enquanto isso, dá pra consultar as
  tabelas que já existem direto via `docker exec <container-db> psql -U postgres -d dados_rfb -c
  "\dt"`.
- **ETL "trava" sem nenhuma mensagem de erro**: suspeite de falta de memória (OOM kill silencioso,
  sem traceback). Confira `docker stats` durante a carga e considere aumentar a memória do Docker
  Desktop (ver seção 2 acima).
- **`docker ps`/`docker inspect`/`docker logs` ficam sem responder (hang) durante a carga
  completa**: normalmente é pressão de recursos (CPU/memória/disco) do próprio ETL rodando no
  mesmo Docker Desktop. Espere terminar ou aumente os recursos alocados ao Docker Desktop; evite
  insistir em repetir o comando em loop.
- **Busca por município retorna 400 "ambíguo"**: nomes de município se repetem entre estados no
  Brasil (ex.: "Bom Jesus" existe em 5 UFs). Use o código numérico da tabela `munic` (o erro lista
  as opções) em vez do nome.
