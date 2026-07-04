# Dados Públicos CNPJ
- Fonte oficial da Receita Federal do Brasil, [aqui](https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj).
- Layout dos arquivos, [aqui](https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf).

A Receita Federal do Brasil disponibiliza bases com os dados públicos do cadastro nacional de pessoas jurídicas (CNPJ).

De forma geral, nelas constam as mesmas informações que conseguimos ver no cartão do CNPJ, quando fazemos uma consulta individual, acrescidas de outros dados de Simples Nacional, sócios e etc. Análises muito ricas podem sair desses dados, desde econômicas, mercadológicas até investigações.

Nesse repositório consta um processo de ETL para **i)** baixar os arquivos; **ii)** descompactar; **iii)** ler, tratar e **iv)** inserir num banco de dados relacional PostgreSQL.

---------------------

### Infraestrutura necessária:
- [Python 3.8](https://www.python.org/downloads/release/python-3810/)
- [PostgreSQL 14.2](https://www.postgresql.org/download/)

---------------------

### How to use:
1. Com o Postgres instalado, inicie a instância do servidor (pode ser local) e crie o banco de dados conforme o arquivo `banco_de_dados.sql`.

2. Crie um arquivo `.env` no diretório `code`, conforme as variáveis de ambiente do seu ambiente de trabalho (localhost). Utilize como referência o arquivo `.env_template`. Você pode também, por exemplo, renomear o arquivo de `.env_template` para apenas `.env` e então utilizá-lo:
   - `OUTPUT_FILES_PATH`: diretório de destino para o donwload dos arquivos
   - `EXTRACTED_FILES_PATH`: diretório de destino para a extração dos arquivos .zip
   - `DB_USER`: usuário do banco de dados criado pelo arquivo `banco_de_dados.sql`
   - `DB_PASSWORD`: senha do usuário do BD
   - `DB_HOST`: host da conexão com o BD
   - `DB_PORT`: porta da conexão com o BD
   - `DB_NAME`: nome da base de dados na instância (`Dados_RFB` - conforme arquivo `banco_de_dados.sql`)

3. Instale as bibliotecas necessárias, disponíveis em `requirements.txt`:
```
pip install -r requirements.txt
```

4. Execute o arquivo `ETL_coletar_dados_e_gravar_BD.py` e aguarde a finalização do processo.
   - Os arquivos são grandes. Dependendo da infraestrutura isso deve levar muitas horas para conclusão.
   - Arquivos de 08/05/2021: `4,68 GB` compactados e `17,1 GB` descompactados.

---------------------

### Rodando via Docker (recomendado para testar localmente)

Alternativa ao passo a passo acima: sobe o Postgres e o ETL em containers, sem precisar instalar
Python/Postgres na máquina.

1. Copie `.env.example` para `.env` na raiz do repo (ajuste se quiser, os valores padrão já
   funcionam) e suba o banco:
   ```
   docker compose up -d db
   ```

2. Rode o ETL dentro do Docker. Por padrão (`.env.example`) ele roda em **modo de teste**
   (`ETL_TEST_MODE=true`), que baixa só 1 arquivo de cada categoria fracionada
   (Empresas/Estabelecimentos/Sócios/Simples) e insere só as primeiras `ETL_MAX_ROWS` linhas de
   cada um — os dados são reais (baixados da Receita Federal de verdade), só que uma fração bem
   menor, útil para testar o fluxo em minutos em vez de horas:
   ```
   docker compose run --rm etl
   ```
   Para rodar a carga **completa** (todos os arquivos, todas as linhas — demora horas e ocupa
   dezenas de GB), defina `ETL_TEST_MODE=false` no `.env` antes de rodar o comando acima.

   > **Nota sobre dados de teste**: como o modo de teste lê só as primeiras linhas de cada
   > arquivo, e os arquivos de `empresa`/`estabelecimento`/`socios`/`simples` não vêm
   > necessariamente alinhados pela mesma faixa de `cnpj_basico`, é possível que um CNPJ
   > específico não tenha registro em todas as tabelas ao mesmo tempo nessa amostra. Isso é
   > esperado — não é um bug. Para testar consultas completas (empresa + sócios + Simples juntos),
   > rode a carga completa ou consulte um `cnpj_basico` que você confirme existir em mais de uma
   > tabela.

3. Suba a API:
   ```
   docker compose up -d api
   ```
   A API sobe em `http://localhost:3000` (Swagger em `http://localhost:3000/docs`).

### API HTTP (NestJS) para consultar os dados

O diretório `api/` tem uma API REST somente-leitura em NestJS por cima do banco, pensada para ser
consumida por outras ferramentas (ex: um fluxo n8n) sem depender de uma API paga de CNPJ.

Endpoints principais:
- `GET /cnpj/:cnpj` — consulta por CNPJ. Aceita 8 dígitos (raiz da empresa, retorna a matriz por
  padrão) ou 14 dígitos (estabelecimento específico). Use `?all=true` com 8 dígitos para listar
  todos os estabelecimentos da raiz. Resposta consolidada com dados cadastrais, endereço, sócios
  (CPF de pessoa física sempre mascarado) e situação no Simples/MEI, com os códigos da Receita já
  traduzidos (situação cadastral, natureza jurídica, CNAE, município, etc.).
- `GET /empresas/search?razao_social=&uf=&municipio=&situacao=&cnae=&page=&limit=` — busca
  paginada por nome/UF/situação/CNAE.
- `GET /health` — checagem simples de saúde (inclui teste de conexão com o banco).
- `GET /docs` — Swagger UI com todos os endpoints.

Sem autenticação por padrão (pensada para uso local/interno) — não exponha essa API além de
localhost ou da rede Docker sem adicionar autenticação antes.

Rodando localmente sem Docker (útil durante desenvolvimento): copie `api/.env.example` para
`api/.env`, `npm install` e `npm run start:dev` dentro de `api/` (aponta para o Postgres exposto
pelo `docker-compose` em `localhost:5432`).

#### Integrando com o n8n

Se o n8n também estiver rodando em um container Docker (ex: Docker Desktop), o jeito mais simples
de chamar a API a partir de um nó HTTP Request do n8n é usando o endereço especial do Docker
Desktop para acessar o host:
```
http://host.docker.internal:3000/cnpj/{{ $json.cnpj }}
```
Isso funciona nativamente no Docker Desktop (Windows/Mac). Se um dia isso for rodar em Linux puro
(sem Docker Desktop), `host.docker.internal` não resolve por padrão — nesse caso, conecte o
container da API à mesma rede do n8n (`docker network connect cnpj-net <container_do_n8n>`) e
chame `http://api:3000/...` em vez disso.

---------------------

### Tabelas geradas:
- Para maiores informações, consulte o [layout](https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/cadastros/consultas/arquivos/NOVOLAYOUTDOSDADOSABERTOSDOCNPJ.pdf).
  - `empresa`: dados cadastrais da empresa em nível de matriz
  - `estabelecimento`: dados analíticos da empresa por unidade / estabelecimento (telefones, endereço, filial, etc)
  - `socios`: dados cadastrais dos sócios das empresas
  - `simples`: dados de MEI e Simples Nacional
  - `cnae`: código e descrição dos CNAEs
  - `quals`: tabela de qualificação das pessoas físicas - sócios, responsável e representante legal.
  - `natju`: tabela de naturezas jurídicas - código e descrição.
  - `moti`: tabela de motivos da situação cadastral - código e descrição.
  - `pais`: tabela de países - código e descrição.
  - `munic`: tabela de municípios - código e descrição.


- Pelo volume de dados, as tabelas  `empresa`, `estabelecimento`, `socios` e `simples` possuem índices para a coluna `cnpj_basico`, que é a principal chave de ligação entre elas.

### Modelo de Entidade Relacionamento:
![alt text](https://github.com/aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ/blob/master/Dados_RFB_ERD.png)