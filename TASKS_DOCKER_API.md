# Tracking: Docker + API NestJS sobre dados de CNPJ

> Arquivo de acompanhamento entre sessões. Objetivo: rodar o ETL de CNPJ via Docker (Postgres +
> import parcial/rápido para testes) e servir os dados via uma API NestJS nova (`api/`) para ser
> consumida por um fluxo n8n (dockerizado, porta 5678) local, substituindo uma API paga durante os
> testes. Plano completo original em `C:\Users\braga\.claude\plans\wondrous-jingling-newell.md`
> (pode não existir mais em sessões futuras — este arquivo é a fonte de verdade que sobrevive).
>
> **Regra**: cada tarefa deve caber numa sessão. Ao concluir uma tarefa, marque o checkbox abaixo
> e adicione uma nota em "Notas de handoff" (o que foi feito, decisões tomadas, o que falta,
> qualquer coisa que destoou do plano original). Ao retomar, leia esse arquivo inteiro antes de
> continuar — não re-derive as decisões abaixo do zero.

## Checklist

- [x] **Tarefa 0** — Criar este arquivo de tracking.
- [x] **Tarefa 1** — Fixes no ETL: guarda `isatty()` + fail-fast de env vars; connection string segura (URL.create/kwargs).
- [x] **Tarefa 2** — Modo de teste rápido no ETL (`ETL_TEST_MODE`/`ETL_MAX_FILES_PER_TYPE`/`ETL_MAX_ROWS`).
- [x] **Tarefa 3a** — Dockerizar DB + ETL (arquivos criados, build ok, `db` sobe healthy).
- [x] **Tarefa 3b (NOVA, não estava no plano original)** — Corrigido: ETL agora descobre e baixa
  os arquivos via WebDAV do Nextcloud oficial da Receita Federal. **Import de teste rodou
  100% de ponta a ponta dentro do Docker** (download real + extração + insert nas 10 tabelas +
  criação de índices). Ver detalhes na nota de handoff.
- [x] **Tarefa 4** — Esqueleto NestJS (`api/`) + módulo de banco (Kysely + pg Pool) + módulo `lookups` (cache em memória) + `/health`. Rodando localmente e verificado contra o Postgres real.
- [x] **Tarefa 5** — Endpoint `GET /cnpj/:cnpj` (core para o n8n). Testado de ponta a ponta,
  inclusive com fixture sintética (matriz+filial+sócios PF/PJ+simples) e casos de erro.
- [x] **Tarefa 6** — Endpoint `GET /empresas/search`. Testado com fixture sintética (3 empresas):
  filtro `razao_social` (ILIKE + paginação), `uf`, `situacao` — todos corretos.
- [x] **Tarefa 7** — Dockerizar a API (`api/Dockerfile`, serviço `api` no compose, Swagger, CORS).
  Stack completa (`db`+`api`) testada via Docker de ponta a ponta.
- [x] **Tarefa 8** — Verificação end-to-end da stack completa + atualizar `README.md`. **PROJETO
  COMPLETO** — todas as 9 tarefas concluídas e verificadas de ponta a ponta.

## Contrato de variáveis de ambiente (congelado — não mudar sem atualizar todas as tarefas)

Raiz do repo, arquivo `.env` (gitignored) + `.env.example` versionado:

```
DB_NAME=dados_rfb
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=db          # nome do serviço no docker network; "localhost" para rodar fora do compose
DB_PORT=5432
DB_HOST_PORT=5432   # porta exposta no host (trocar se 5432 já estiver em uso)

ETL_TEST_MODE=true
ETL_MAX_FILES_PER_TYPE=1
ETL_MAX_ROWS=5000

OUTPUT_FILES_PATH=/data/output       # caminho DENTRO do container etl
EXTRACTED_FILES_PATH=/data/extracted # caminho DENTRO do container etl

API_PORT=3000
```

`docker-compose.yml` traduz `DB_NAME/DB_USER/DB_PASSWORD` para `POSTGRES_DB/POSTGRES_USER/POSTGRES_PASSWORD`
no serviço `db` (não renomear a convenção `DB_*` já usada em `code/.env_template`, que continua
valendo para quem rodar o ETL fora do Docker). `banco_de_dados.sql` não é usado no fluxo Docker —
`POSTGRES_DB=dados_rfb` já cria o banco no init do Postgres.

## Schema do banco (referência — não re-derivar do script em cada tarefa)

Tabelas criadas implicitamente pelo pandas `to_sql` no ETL (sem PK/FK, só índices em `cnpj_basico`
para empresa/estabelecimento/socios/simples):

- `empresa(cnpj_basico text, razao_social text, natureza_juridica int, qualificacao_responsavel int, capital_social float, porte_empresa int, ente_federativo_responsavel text)`
- `estabelecimento(cnpj_basico text, cnpj_ordem text, cnpj_dv text, identificador_matriz_filial int, nome_fantasia text, situacao_cadastral int, data_situacao_cadastral, motivo_situacao_cadastral int, nome_cidade_exterior text, pais int, data_inicio_atividade, cnae_fiscal_principal int, cnae_fiscal_secundaria text (códigos separados por vírgula), tipo_logradouro text, logradouro text, numero text, complemento text, bairro text, cep text, uf text, municipio int, ddd_1/telefone_1/ddd_2/telefone_2/ddd_fax/fax text, correio_eletronico text, situacao_especial text, data_situacao_especial)`
- `socios(cnpj_basico text, identificador_socio int, nome_socio_razao_social text, cpf_cnpj_socio text, qualificacao_socio int, data_entrada_sociedade int, pais int, representante_legal text, nome_do_representante text, qualificacao_representante_legal int, faixa_etaria int)`
- `simples(cnpj_basico text, opcao_pelo_simples text S/N, data_opcao_simples int, data_exclusao_simples int, opcao_mei text S/N, data_opcao_mei int, data_exclusao_mei int)`
- `cnae(codigo, descricao)`, `moti(codigo, descricao)`, `munic(codigo, descricao)`, `natju(codigo, descricao)`, `pais(codigo, descricao)`, `quals(codigo, descricao)` — lookups pequenos.

**TIPOS REAIS CONFIRMADOS** (via `information_schema.columns` após carga de teste real — Tarefa 3b,
não são mais suposição a partir do dtype do pandas):
- `cnae.codigo` = **text**; `moti.codigo`/`munic.codigo`/`natju.codigo`/`pais.codigo`/`quals.codigo` = **integer**.
- `estabelecimento.cnae_fiscal_principal` = **integer** → **mismatch com `cnae.codigo` (text)**.
- `estabelecimento.pais` = **text** (não é integer, ao contrário do que a doc original supunha)
  → **também mismatch com `pais.codigo` (integer)**.
- `estabelecimento.municipio` = integer → bate certo com `munic.codigo` (integer).
- `socios.pais` = integer → bate certo com `pais.codigo` (integer). Únicas duas colunas de
  código com mismatch de tipo confirmadas são `estabelecimento.cnae_fiscal_principal`↔`cnae.codigo`
  e `estabelecimento.pais`↔`pais.codigo`.
- **Por isso a decisão de resolver todos os lookups em memória no código da API (não via SQL
  join) é ainda mais importante do que se pensava** — normalizar ambos os lados para string
  resolve os dois mismatches de uma vez, sem precisar de casts diferentes por tabela.
- Todas as colunas de texto (`cnpj_basico`, `cnpj_ordem`, `cnpj_dv`, endereço, telefones, etc.)
  confirmadas como `text`, nenhuma perdeu zero à esquerda.

CNPJ completo = `cnpj_basico`(8) + `cnpj_ordem`(4) + `cnpj_dv`(2), como colunas de **texto**
separadas em `estabelecimento` (nunca tratar como número — perde zero à esquerda).

## Decisões de design (válidas para todas as tarefas)

- **Acesso a dados na API: Kysely** (query builder tipado sobre `pg`), não TypeORM/Prisma — as
  tabelas não têm PK e o schema é recriado pelo ETL a cada carga.
- **Lookups em memória**: `cnae`, `moti`, `munic`, `natju`, `pais`, `quals` carregadas inteiras no
  boot da API e resolvidas em código (evita mismatch de tipo do cnae e resolve
  `cnae_fiscal_secundaria`, que é uma lista de códigos separados por vírgula, numa só passada).
- **CPF sempre mascarado**: `socios.cpf_cnpj_socio` com 11 dígitos (pessoa física) sempre
  mascarado antes de retornar na API; com 14 dígitos (pessoa jurídica) passa direto. Não
  configurável — é uma ferramenta interna, não há motivo para expor CPF cru.
- **CNPJ na query**: normalizar removendo não-dígitos; 14 dígitos = estabelecimento específico
  (`cnpj_basico`+`cnpj_ordem`, sem exigir bater o `cnpj_dv`, apenas retorná-lo na resposta); 8
  dígitos = matriz por padrão (`?all=true` lista todos os estabelecimentos).
- **Sem autenticação por padrão** (uso local/teste), CORS liberado, Swagger em `/docs`. Documentar
  no README que isso não deve ser exposto além de localhost/rede docker sem adicionar auth.
- **n8n**: chama a API via `http://host.docker.internal:3000/...` (Docker Desktop Windows resolve
  nativamente). Alternativa: `docker network connect cnpj-net <container_n8n>` + `http://api:3000`.

## Notas de handoff

- **Tarefa 0** (concluída): arquivo criado com o plano completo transcrito do plano aprovado em
  `C:\Users\braga\.claude\plans\wondrous-jingling-newell.md`. Nada de código foi tocado ainda.
- **Tarefa 1** (concluída): em `code/ETL_coletar_dados_e_gravar_BD.py`:
  - `input()` só é chamado se `.env` não existir **e** `sys.stdin.isatty()` (não trava mais em
    container não-interativo).
  - Fail-fast logo após `load_dotenv`: checa `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME/
    OUTPUT_FILES_PATH/EXTRACTED_FILES_PATH` e sai com `sys.exit(mensagem)` se faltar algo (removeu
    o `try/except: pass` que engolia o erro e seguia com `output_files=None`).
  - Connection string trocada para `sqlalchemy.engine.URL.create(...)` (import `from
    sqlalchemy.engine import URL` adicionado) e `psycopg2.connect(dbname=..., user=..., host=...,
    port=..., password=...)` via kwargs — antes era concatenação de string, quebrava com senha
    contendo `@`/`:`/`/`/espaço.
  - Validado com `python -m py_compile` — sintaxe OK (só um `SyntaxWarning` pré-existente e não
    relacionado, de uma string com `\.` no print da linha ~77 — fora do escopo desta tarefa, não
    mexi).
- **Tarefa 2** (concluída): ainda em `code/ETL_coletar_dados_e_gravar_BD.py`:
  - Novas env vars lidas logo após `Files = Files_clean`: `ETL_TEST_MODE` (bool), `
    ETL_MAX_FILES_PER_TYPE` (int ou None), `ETL_MAX_ROWS` (int ou None).
  - Função `limit_files_per_type(files, max_per_type)` filtra a lista `Files` mantendo só os N
    primeiros de cada categoria fracionada (`EMPRE`/`ESTABELE`/`SOCIO`/`SIMPLES`); arquivos de
    lookup (cnae/moti/munic/natju/pais/quals) não batem em nenhuma keyword e passam direto, sem
    limite — aplicada só quando `ETL_TEST_MODE` é true.
  - `nrows=ETL_MAX_ROWS` adicionado nos `read_csv` de `empresa` e `socios` (era `None` quando não
    setado, ou seja, sem limite — comportamento full-import inalterado).
  - `estabelecimento`: `NROWS = ETL_MAX_ROWS or 2000000`; condição de continuar o loop virou
    `if len(estabelecimento) == NROWS and not ETL_TEST_MODE: part += 1 else: break` — em test
    mode sempre para na 1ª iteração, não fica lendo o arquivo inteiro em pedacinhos.
  - `simples`: em test mode pula o `sum(1 for line in open(...))` (passada de I/O sobre o
    arquivo inteiro) e faz `partes=1, nrows=ETL_MAX_ROWS, skiprows=0` direto.
  - Confirmado via `grep nrows` que as 6 tabelas de lookup não foram tocadas (continuam sem
    `nrows`, carregando completas sempre).
  - Validado com `python -m py_compile` — sintaxe OK (mesmo warning pré-existente de antes, não
    relacionado).
  - **Não testado ainda rodando de verdade** (isso só é possível dentro do Docker, ver Tarefa 3) —
    a lógica foi revisada por leitura mas o primeiro teste real com dados da RF só acontece na
    verificação da Tarefa 3.
- **Tarefa 3a** (parcialmente concluída — infra Docker ok, import real bloqueado por causa
  externa ao repo):
  - Criados: `code/Dockerfile` (build context é a RAIZ do repo, não `code/`, porque
    `requirements.txt` mora na raiz — desvio pequeno e deliberado do plano original, que dizia
    "code/Dockerfile" com contexto implícito em `code/`), `.dockerignore` na raiz, `.env.example`
    na raiz (igual ao contrato congelado acima), `docker-compose.yml` na raiz com serviços `db`
    (postgres:16-alpine, healthcheck) e `etl` (profile `etl`, só roda via `docker compose run
    --rm etl`), `.gitignore` atualizado (+`/data/`, `node_modules/`, `api/dist/`).
  - **Achado não-óbvio**: o nome da pasta do projeto (`Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ`)
    tem maiúsculas/hífen — Docker deriva o "nome do projeto compose" do nome da pasta e usa isso
    como tag de imagem, e tags de imagem Docker não podem ter maiúsculas → build falhava com
    "invalid tag". Fix: adicionei `name: cnpj-rfb` no topo do `docker-compose.yml` para fixar o
    nome do projeto explicitamente. **Isso é necessário sempre que rodar docker compose neste
    repo** — sem isso, `docker compose build`/`run` falha.
  - `docker compose up -d db` → healthy confirmado. `docker compose --profile etl build etl` →
    build ok (Python 3.11-slim + requirements.txt, ~20s).
  - `docker compose run --rm etl` **rodou** (não travou! confirma que o fix da Tarefa 1 funciona:
    imprimiu `/app/.env`, "Diretórios definidos: output_files: /data/output extracted_files:
    /data/extracted" e seguiu em frente sem pedir input) — mas quebrou logo depois com
    `ConnectionRefusedError` ao tentar `urllib.request.urlopen('http://200.152.38.155/CNPJ/')`.
  - **Investiguei e confirmei que NÃO é um bug do Docker/rede do container**: `curl` desse mesmo
    IP direto da máquina host também falha (connection refused). Pesquisei e descobri que a
    Receita Federal migrou a hospedagem dos dados abertos por volta de jan/2026 para um portal
    baseado em Nextcloud (`https://arquivos.receitafederal.gov.br/index.php/s/...`), que exige
    JS/sessão para listar arquivos — não é mais um diretório Apache simples com HTML estático,
    que é o que a lógica atual de scraping (`BeautifulSoup` + regex procurando `.zip`/`href=`)
    espera. Um mirror de terceiros (`https://dados-abertos-rf-cnpj.casadosdados.com.br/`) também
    parece ser um site dinâmico (Cloudflare, `text/html` sem indício de listagem simples), não
    testado a fundo.
  - **Isso bloqueia qualquer import real, com ou sem Docker, com ou sem modo de teste** — é um
    problema pré-existente no repo (a URL hardcoded há tempos), só que só aparece quando alguém
    de fato tenta rodar o download, e ninguém tinha rodado ainda nesta sessão até agora.
  - Estado atual dos containers: `db` está `Up (healthy)` (deixei rodando, é inofensivo). Container
    `etl` não fica parado (rodou com `--rm`).
  - **Não decidi a correção sozinho** porque isso muda parte do escopo do plano original (a lógica
    de descoberta de arquivos, não só variáveis de ambiente) e existem pelo menos 2 caminhos
    (WebDAV do Nextcloud oficial vs. mirror de terceiros) com trade-offs que acho melhor validar
    com o usuário antes de implementar. Ver pergunta feita na sessão em que isso foi descoberto.
- **Tarefa 3b** (concluída — CORRIGIDO E VERIFICADO DE PONTA A PONTA):
  - Perguntei ao usuário como preferia resolver (Nextcloud oficial vs. mirror vs. ele já saber a
    URL) via AskUserQuestion; não respondeu em 60s, então segui com a opção recomendada
    (investigar a API oficial do Nextcloud) por conta própria, dado o modo autônomo ativo.
  - **Descoberta**: o compartilhamento público oficial da RF
    (`https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9`, achado via busca web,
    referenciado como fonte primária a partir de dados.gov.br) é servido por Nextcloud e expõe um
    endpoint WebDAV padrão em `https://arquivos.receitafederal.gov.br/public.php/webdav/`,
    autenticável via HTTP Basic com o token do link como usuário e senha vazia (`curl -X PROPFIND
    -u "TOKEN:" -H "Depth: 1" .../public.php/webdav/` funciona, testado manualmente antes de
    mexer no código). A raiz lista pastas `AAAA-MM` (uma por mês de referência, ex: `2026-06`);
    dentro de cada uma estão os 33 arquivos zip de sempre (`Empresas0-9.zip`,
    `Estabelecimentos0-9.zip`, `Socios0-9.zip`, `Simples.zip`, `Cnaes.zip`, `Motivos.zip`,
    `Municipios.zip`, `Naturezas.zip`, `Paises.zip`, `Qualificacoes.zip`).
  - **Mudanças em `code/ETL_coletar_dados_e_gravar_BD.py`**:
    - Removidos `import bs4 as bs` e `import wget` (não usados mais); adicionados
      `import urllib.parse` e `import xml.etree.ElementTree as ET`.
    - Novo bloco `RF_WEBDAV_BASE` / `RF_SHARE_TOKEN` (override via env var opcional
      `ETL_RF_SHARE_TOKEN`, caso a RF troque o link novamente) / `RF_AUTH = (token, '')`.
    - Nova função `webdav_list(path)` faz `PROPFIND` (via `requests.request('PROPFIND', ...)`)
      e retorna os nomes dos itens da pasta.
    - Descobre o mês mais recente (`sorted(...)[-1]` sobre pastas que batem `\d{4}-\d{2}`) e monta
      `dados_rf` + `Files` a partir da listagem WebDAV daquele mês — substitui 100% a raspagem de
      HTML antiga.
    - `check_diff` e o novo `download_file(url, output_dir, auth=RF_AUTH)` (substituiu
      `wget.download`, que não suporta autenticação) passam `auth=RF_AUTH` no `requests`.
    - `requirements.txt`: removidas `beautifulsoup4`, `bs4`, `lxml`, `soupsieve`, `wget` (só
      serviam para a raspagem antiga).
  - **Verificação real, dentro do Docker** (`docker compose run --rm etl` com
    `ETL_TEST_MODE=true`, `ETL_MAX_FILES_PER_TYPE=1`, `ETL_MAX_ROWS=5000`):
    - Baixou os 10 arquivos esperados de `2026-06/` de verdade (progresso real de bytes visto no
      log, ex: `Estabelecimentos0.zip` ~2.1GB, `Simples.zip` ~297MB, `Socios0.zip` ~236MB — ou
      seja, mesmo em "modo teste" o download baixa o arquivo inteiro, só a INSERÇÃO é limitada a
      5000 linhas; não é um teste rápido em banda larga limitada, mas terminou em poucos minutos
      aqui), extraiu, e inseriu com sucesso.
    - Rodou o processo completo (inclusive criação de índices) em ~2s de processamento de dados
      (por causa do cap de 5000 linhas) mais o tempo de download/extração.
    - Contagem final confirmada via `psql`: `empresa=5000, estabelecimento=5000, socios=5000,
      simples=5000, cnae=1359, moti=63, munic=5572, natju=91, pais=255, quals=68` — as 6 tabelas
      de lookup vieram **completas** (não limitadas), exatamente como projetado na Tarefa 2.
    - Tipos reais de coluna confirmados via `information_schema.columns` — ver seção "Schema do
      banco" acima, atualizada com os valores reais (2 mismatches de tipo confirmados:
      cnae/estabelecimento.cnae_fiscal_principal e pais/estabelecimento.pais).
  - **Achado extra sobre o nome do projeto Docker**: a pasta do repo tem maiúsculas/hífen no
    nome, o que quebra a derivação automática do nome do projeto compose (usado como tag de
    imagem, que não pode ter maiúsculas). Precisei adicionar `name: cnpj-rfb` no topo do
    `docker-compose.yml` — sem isso, `docker compose build`/`run` falha com "invalid tag". **Isso
    já está no `docker-compose.yml` commitado, não precisa refazer.**
  - Estado deixado ao final: container `db` rodando e healthy (útil, deixei de propósito);
    container `etl` não fica parado (`--rm`). Dados de teste (5000 linhas por tabela grande) JÁ
    ESTÃO no banco agora — útil para testar a API nas próximas tarefas sem precisar rodar o ETL de
    novo.
  - Próximo passo: **Tarefa 4** (esqueleto NestJS). O banco já está populado com dados de teste
    reais, então a partir daqui já dá pra testar os endpoints da API contra dados de verdade
    assim que existirem.

- **Tarefa 4** (concluída e verificada rodando de verdade):
  - Projeto `api/` criado à mão (não via `nest new`, para controlar exatamente os arquivos):
    `package.json` (Nest 10.x, `kysely` ^0.27, `pg` ^8.12, `@nestjs/config`, `@nestjs/swagger` já
    incluído nas deps para a Tarefa 7), `tsconfig.json`, `nest-cli.json`, `.env.example` (local,
    aponta pro Postgres exposto em `localhost:5432` pelo compose — diferente do `.env.example` da
    raiz, que usa `DB_HOST=db` para dentro da rede Docker).
  - `src/database/database.module.ts`: módulo `@Global()` expondo um `Kysely<Database>` via
    token `KYSELY_CONNECTION` (Symbol), configurado com `pg.Pool` a partir de env vars.
  - `src/database/database.types.ts`: interfaces Kysely para as 10 tabelas, já usando os TIPOS
    REAIS confirmados na Tarefa 3b (ex: `cnae.codigo: string`, `estabelecimento.pais: string`).
  - `src/lookups/lookups.service.ts` (+ `lookups.module.ts`, também `@Global()`): carrega as 6
    tabelas de referência em `Map<string, string>` no `onModuleInit`, normalizando `codigo` para
    string em ambos os lados (resolve os 2 mismatches de tipo de uma vez). Expõe
    `resolveCnae/resolveMotivoSituacaoCadastral/resolveMunicipio/resolveNaturezaJuridica/
    resolvePais/resolveQualificacao` e `resolveCnaeSecundarias` (para a lista separada por
    vírgula de `cnae_fiscal_secundaria`). Método público `refresh()` para recarregar sem reiniciar
    o processo, se um dia for preciso.
  - `src/health/health.controller.ts`: `GET /health` faz `select 1` via Kysely (`sql` tag) e
    retorna `{status, db}`.
  - `src/app.module.ts` / `src/main.ts`: `ConfigModule.forRoot({isGlobal:true})`, CORS liberado
    (`app.enableCors()`), porta via `process.env.PORT` (default 3000). Swagger fica para a Tarefa 7
    (precisa de DTOs que só existem a partir da Tarefa 5).
  - **Verificado de verdade, não só compilado**: `npm install` + `npm run build` sem erros;
    rodei `npm run start` local (Node 24 na máquina do usuário) contra o `db` do docker-compose
    (que já tinha os dados de teste da Tarefa 3b, ainda rodando) — log mostrou
    `Lookups carregados: cnae=1359, moti=63, munic=5572, natju=91, pais=255, quals=68` (bate
    exatamente com as contagens reais do Postgres) e `curl http://localhost:3000/health` retornou
    `{"status":"ok","db":true}`.
  - **Estado deixado ao final**: processo `npm run start` da API ficou rodando em background
    (não é `--watch`, então mudanças de código exigem reiniciar manualmente antes de testar). `db`
    do Docker continua healthy com os dados de teste. Se for continuar na Tarefa 5, é só reiniciar
    o `npm run start` depois de criar os arquivos novos.
  - Próximo passo: **Tarefa 5** — endpoint `GET /cnpj/:cnpj`, o principal consumido pelo n8n.

- **Tarefa 5** (concluída e verificada com testes reais + fixture sintética):
  - Novos: `src/common/rf-codes.ts` (mapas fixos `SITUACAO_CADASTRAL`, `IDENTIFICADOR_MATRIZ_FILIAL`,
    `PORTE_EMPRESA`, `FAIXA_ETARIA`, `IDENTIFICADOR_SOCIO` + helper `lookupCode`, do layout da RF —
    reutilizável pela Tarefa 6), `src/common/cpf-mask.ts` (`maskCpf`, só mascara se tiver
    exatamente 11 dígitos), `src/cnpj/{cnpj.module.ts,cnpj.controller.ts,cnpj.service.ts}`.
  - `GET /cnpj/:cnpj` (`?all=true` opcional) normaliza dígitos, aceita 8 ou 14, roda 3 queries em
    paralelo (estabelecimento+empresa, socios, simples) via `Promise.all`. 400 se não tiver 8 ou
    14 dígitos; 404 se `cnpj_basico` não existir; 404 se 14 dígitos e a `cnpj_ordem` não existir.
  - **ACHADO IMPORTANTE (confirmado com dados reais, não é bug do meu código)**: com a amostra de
    teste (5000 linhas por tabela, Tarefa 2/3b), **`empresa` e `estabelecimento` não têm nenhum
    `cnpj_basico` em comum** (`select count(*) from estabelecimento e join empresa ...` = 0) —
    os arquivos da Receita Federal não vêm alinhados por essa chave quando se lê só as primeiras N
    linhas de cada um (não são a mesma fatia do keyspace). **Isso vale para qualquer sessão futura
    testando com `ETL_TEST_MODE`**: não espere achar um CNPJ com `empresa`+`estabelecimento`+
    `socios` todos preenchidos de verdade nessa amostra pequena; ou usa fixture sintética (como
    fiz abaixo) ou roda o import completo (sem `ETL_TEST_MODE`) para testar isso de verdade.
  - **Fix decorrente**: troquei `innerJoin('empresa', ...)` por `leftJoin(...)` na query principal
    — com INNER, esse gap de dados faria o endpoint voltar 404 pra QUALQUER `cnpj_basico` da
    amostra de teste, mesmo com o estabelecimento existindo. Testei contra um `cnpj_basico` real
    (`63621960`, só em `estabelecimento`) e confirmei: retorna 200 com `razao_social: null` (e os
    outros campos só de `empresa` como null), mas todo o resto (situação cadastral, CNAE
    principal+secundárias, município) veio resolvido corretamente pelos lookups.
  - **Verificação completa via fixture sintética** (inserida e removida via `psql` direto,
    `cnpj_basico='99999999'`, não sobrou no banco): 1 empresa, matriz (`0001`) + filial (`0002`),
    2 sócios (1 pessoa física com CPF, 1 pessoa jurídica com CNPJ) e 1 registro de Simples/MEI.
    Testei os 3 modos:
    - `GET /cnpj/99999999` (8 dígitos, default) → retornou a matriz, `total_estabelecimentos: 2`.
    - `GET /cnpj/99999999000272` (14 dígitos) → retornou a filial certa (ordem `0002`).
    - `GET /cnpj/99999999?all=true` → retornou os 2 estabelecimentos numa lista.
    - Confirmado: CPF do sócio pessoa física veio mascarado (`"123.***.***-00"`), CNPJ do sócio
      pessoa jurídica veio sem máscara (`"11222333000181"`) — exatamente como projetado.
    - Confirmado: todos os lookups resolvidos certo (natureza jurídica, qualificação, município,
      país, faixa etária, CNAE principal + secundárias).
    - Casos de erro testados: CNPJ com formato inválido → 400; CNPJ de 8 dígitos inexistente →
      404; CNPJ de 14 dígitos com `cnpj_ordem` inexistente → 404.
  - **Estado deixado ao final**: fixture sintética REMOVIDA do banco (não sobrou lixo). Processo
    `npm run start` da API continua rodando em background na porta 3000 (reiniciado depois do
    build mais recente). `db` do Docker continua com os 5000 registros de teste de cada tabela
    grande (da Tarefa 3b).
  - Próximo passo: **Tarefa 6** — endpoint `GET /empresas/search`.

- **Tarefa 6** (concluída e verificada com fixture sintética):
  - Novos: `src/empresas/{empresas.module.ts,empresas.controller.ts,empresas.service.ts}`.
  - `GET /empresas/search?razao_social=&uf=&municipio=&situacao=&cnae=&page=&limit=` — filtros
    opcionais via `.$if()` do Kysely (nenhuma concatenação manual de SQL — mesmo o `ILIKE` usa
    bind parameter, sem risco de injection), `count(*) over()` pra total sem round-trip extra
    (Postgres retorna `bigint` como string via `pg`, por isso `Number(rows[0].total_count)`).
    `limit` capado em 100, `page` mínimo 1. `uf` normalizado pra maiúsculo.
  - **Essa query usa INNER JOIN (não LEFT como a Tarefa 5)** — decisão deliberada: numa busca por
    nome de empresa não faz sentido devolver linha sem `razao_social`. Consequência esperada: com
    a amostra de teste de 5000 linhas (que não tem overlap `empresa`↔`estabelecimento`, achado da
    Tarefa 5), **a busca sempre retorna `total: 0`** contra os dados reais de teste - não é bug,
    testei e confirmei isso primeiro (`GET /empresas/search?limit=5` → `{"total":0,...}`) antes de
    validar a lógica de verdade com fixture.
  - **Verificação real com fixture sintética** (3 empresas `88888801/02/03`, inserida e REMOVIDA
    via `psql`, não sobrou no banco): `razao_social=acme&limit=1&page=1` → 2 resultados no total,
    página 1 traz "ACME COMERCIO LTDA" (ordem alfabética correta antes de "ACME SOLUCOES"), página
    2 traz o outro, `total:2, total_pages:2` corretos. `uf=rj` (minúsculo) → 1 resultado, UF
    normalizada e batendo. `situacao=2` → os 3 resultados. Todos com `municipio_descricao` e
    `cnae_fiscal_principal_descricao` resolvidos certo via `LookupsService`.
  - **Estado deixado ao final**: fixture removida, banco só com os 5000 registros de teste da
    Tarefa 3b. API rodando em background na porta 3000 (mesmo processo, não precisou reiniciar
    pra essa tarefa - só reiniciei uma vez logo depois do build).
  - Próximo passo: **Tarefa 7** — Dockerizar a API (Dockerfile + serviço no compose) e adicionar
    Swagger/CORS (CORS já está ligado desde a Tarefa 4, falta só o Swagger).

- **Tarefa 7** (concluída e verificada 100% via Docker, não só localmente):
  - `src/main.ts`: adicionado `@nestjs/swagger` (`DocumentBuilder` + `SwaggerModule.setup('docs', ...)`).
    `@ApiTags`/`@ApiOperation`/`@ApiQuery` adicionados nos 3 controllers (cnpj, empresas, health)
    para agrupar e documentar os query params no Swagger UI. Não criei classes DTO decoradas para
    o corpo das respostas (os retornos continuam objetos simples/inferidos) — ficaria mais
    completo com `@ApiProperty` em cada campo, mas é um esforço maior que não pedi pra mim mesmo
    fazer agora; documentado aqui como possível melhoria futura se quiserem o schema de resposta
    completo no Swagger.
  - `api/Dockerfile`: multi-stage `node:22-alpine` (build → `npm install` + `npm run build`;
    runtime → só `npm install --omit=dev` + `dist/`). Usei Node 22 (não 20 como no plano
    original) porque a máquina do usuário já tem Node 24 instalado — 22 é a LTS mais atual
    disponível, mais consistente com o ambiente real do que a sugestão original do plano.
  - `api/.dockerignore`: `node_modules`, `dist`, `.env`, `*.log`.
  - `docker-compose.yml`: serviço `api` adicionado (build `./api`, depende de `db` healthy, env
    vars do contrato congelado, porta `${API_PORT:-3000}:3000`).
  - **Verificação real via Docker** (não só `npm run start` local): `docker compose build api` →
    build ok (~60s). `docker compose up -d db api` → os dois sobem, `api` fica `Up` sem healthcheck
    próprio (não configurei um; poderia adicionar depois se quiser). Com os dois containers
    rodando (`api` chamando `db` pelo nome do serviço Docker, `DB_HOST=db`, não `localhost`):
    - `GET /health` → `{"status":"ok","db":true}`.
    - `GET /cnpj/63621960` (mesmo CNPJ real de teste da Tarefa 5) → 200 com os dados esperados.
    - `GET /docs` → 200 (Swagger UI). `GET /docs-json` → 200 com o OpenAPI spec válido.
    - CORS confirmado de verdade: `curl -H "Origin: http://example.com" .../health` retornou
      `Access-Control-Allow-Origin: *`.
  - **Estado deixado ao final**: containers `db` e `api` rodando via `docker compose up -d db api`
    (não mais o `npm run start` local — esse processo foi encerrado antes de buildar a imagem).
    Ambos na rede `cnpj-net`, prontos pro n8n conectar via `host.docker.internal:3000` ou via rede
    Docker compartilhada.
  - Próximo passo: **Tarefa 8** — verificação end-to-end final (incluindo teste simulando o n8n
    via `host.docker.internal`) + atualizar `README.md`.

- **Tarefa 8** (concluída — PROJETO COMPLETO):
  - **Teste simulando o n8n de verdade**: rodei um container isolado (`docker run --rm
    curlimages/curl ...`), numa rede Docker diferente da `cnpj-net` (sem `docker network connect`,
    de propósito, pra simular exatamente a situação de um container de n8n separado) chamando
    `http://host.docker.internal:3000/health` → `200 {"status":"ok","db":true}`. Confirma que a
    recomendação do README (usar `host.docker.internal` no Docker Desktop) funciona de verdade.
  - `README.md` atualizado com 2 seções novas: "Rodando via Docker" (passo a passo `docker
    compose up -d db` → `docker compose run --rm etl` → `docker compose up -d api`, com nota
    explícita sobre o gap de overlap entre tabelas no modo de teste, achado na Tarefa 5) e "API
    HTTP (NestJS) para consultar os dados" (endpoints, como rodar localmente sem Docker, e como
    integrar com o n8n via `host.docker.internal` ou `docker network connect`).
  - Confirmado `git status`: nenhum arquivo indevido seria commitado (`.env`, `api/node_modules`,
    `api/dist` todos corretamente ignorados - verifiquei com `git check-ignore -v`). Nada foi
    commitado nesta sessão (só arquivos no working tree) — o usuário decide quando commitar.
  - **Estado final deixado rodando**: `docker compose up -d db api` — os 2 containers de pé,
    saudáveis, com os ~5000 registros de teste de cada tabela grande (da Tarefa 3b) no banco.
    Não deixei nenhum processo `npm run start` local rodando (só os containers Docker).
  - **Resumo do que NÃO foi feito** (fora do escopo pedido, mas vale saber): não tem testes
    automatizados (unitários/e2e) pra API; não tem CI; não tem autenticação na API (deliberado,
    uso local); Swagger não tem `@ApiProperty` decorando cada campo de resposta (schema completo
    fica mais rico com isso, mas não é essencial pro n8n consumir via HTTP Request node); não
    recriei `banco_de_dados.sql` pro fluxo Docker (não precisa, `POSTGRES_DB` já cuida disso).
