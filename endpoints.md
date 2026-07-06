# Endpoints da API

Referência dos endpoints da API somente-leitura em `api/`. Para subir o ambiente, veja o
`INSTRUCTIONS.md`; para o histórico de decisões de implementação, veja `TASKS_DOCKER_API.md`.

Stack: NestJS + Kysely (query builder, sem ORM) sobre o Postgres populado pelo ETL. Sem
autenticação — uso local/interno.

- Base URL: `http://localhost:3000`
- Swagger (documentação interativa, gerada a partir do mesmo código): `http://localhost:3000/docs`

## GET /health

Checagem simples de saúde, incluindo teste de conexão com o banco (`select 1`).

```
curl http://localhost:3000/health
```

**Resposta 200** (sempre 200, mesmo em erro de banco — o status vem no corpo):
```json
{ "status": "ok", "db": true }
```
Se a conexão com o banco falhar: `{ "status": "error", "db": false }`.

## GET /cnpj/:cnpj

Consulta consolidada de um CNPJ: dados cadastrais, endereço, sócios (CPF sempre mascarado) e
situação no Simples/MEI, com os códigos da Receita Federal já traduzidos para descrição.

- `:cnpj` — 8 dígitos (raiz/matriz) ou 14 dígitos (estabelecimento específico), com ou sem
  formatação (pontos/barra/hífen são ignorados).
- `?all=true` — só tem efeito com 8 dígitos: retorna todos os estabelecimentos da raiz em vez de
  só a matriz.

```
curl http://localhost:3000/cnpj/11222333
curl http://localhost:3000/cnpj/11222333000181
curl "http://localhost:3000/cnpj/11222333?all=true"
```

**Comportamento por formato:**
| Entrada | Resultado |
|---|---|
| 14 dígitos | Um único estabelecimento (o dessa ordem/dv específica) |
| 8 dígitos, sem `all` | A matriz (ordem `0001`; se não existir, o primeiro em ordem crescente) |
| 8 dígitos, com `all=true` | Todos os estabelecimentos da raiz, num array `estabelecimentos` |

**Respostas:**
- `200` — encontrado.
- `400` — quantidade de dígitos inválida (nem 8 nem 14).
- `404` — CNPJ (ou o estabelecimento específico de 14 dígitos) não encontrado.

**Campos principais do objeto de estabelecimento** (achatado na resposta de 14 dígitos / 8 dígitos
sem `all`, ou dentro de cada item de `estabelecimentos` com `all=true`):

- `cnpj`, `cnpj_basico`, `cnpj_ordem`, `cnpj_dv`
- `identificador_matriz_filial` + `_descricao` (Matriz/Filial)
- `razao_social`, `nome_fantasia`
- `situacao_cadastral` + `_descricao` (Nula/Ativa/Suspensa/Inapta/Baixada), `data_situacao_cadastral`
- `motivo_situacao_cadastral` + `_descricao` (via tabela `moti`)
- `data_inicio_atividade`
- `natureza_juridica` + `_descricao` (via tabela `natju`)
- `qualificacao_responsavel` + `_descricao` (via tabela `quals`)
- `capital_social`, `porte_empresa` + `_descricao`, `ente_federativo_responsavel`
- `atividade_principal: { codigo, descricao }` (CNAE, via tabela `cnae`)
- `atividades_secundarias: [{ codigo, descricao }, ...]`
- `endereco: { tipo_logradouro, logradouro, numero, complemento, bairro, cep, uf, municipio, municipio_descricao, pais, pais_descricao, nome_cidade_exterior }`
- `contato: { ddd_1, telefone_1, ddd_2, telefone_2, ddd_fax, fax, email }`
- `situacao_especial`, `data_situacao_especial`
- `total_estabelecimentos` — presente tanto em `all=true` quanto no default de 8 dígitos (conta
  quantos estabelecimentos existem na raiz, mesmo mostrando só a matriz)

**Sempre presentes na resposta (independente do formato de entrada), no nível raiz:**
- `socios: [...]` — cada sócio com `identificador_socio` + `_descricao`, `nome`, `cpf_cnpj`
  (CPF mascarado como `123.***.***-45`, CNPJ passa direto), `qualificacao` + `_descricao`,
  `data_entrada_sociedade`, `pais` + `_descricao`, `representante_legal`,
  `nome_do_representante`, `qualificacao_representante_legal` + `_descricao`, `faixa_etaria` +
  `_descricao`.
- `simples` — `null` se não há registro na tabela `simples` para essa raiz, senão
  `{ opcao_pelo_simples (bool), data_opcao_simples, data_exclusao_simples, opcao_mei (bool), data_opcao_mei, data_exclusao_mei }`.

Com `all=true`, a resposta de topo é `{ cnpj_basico, razao_social, total_estabelecimentos, estabelecimentos: [...], socios, simples }`
em vez de um único estabelecimento achatado.

## GET /empresas/search

Busca paginada por nome, UF, município, situação cadastral e/ou CNAE. Todos os filtros são
opcionais e combináveis (AND); sem nenhum filtro, lista tudo em ordem alfabética de razão social.

| Parâmetro | Tipo | Observações |
|---|---|---|
| `razao_social` | string | `ILIKE %valor%` (contém, case-insensitive) |
| `uf` | string | Sigla, ex: `RJ` |
| `municipio` | string | Nome (ex: `Rio de Janeiro`) **ou** código da tabela `munic`. Nome ambíguo entre estados (ex: "Bom Jesus") retorna 400 listando os códigos possíveis |
| `situacao` | número | `1`=Nula `2`=Ativa `3`=Suspensa `4`=Inapta `8`=Baixada |
| `cnae` | número | CNAE fiscal principal, com ou sem formatação (`8630501` ou `8630-5/01`) — **um único código por chamada**, não há busca por categoria/faixa |
| `page` | número | Padrão `1` |
| `limit` | número | Padrão `20`, máximo `100` |

```
curl "http://localhost:3000/empresas/search?razao_social=exemplo&uf=RJ&limit=10"
curl "http://localhost:3000/empresas/search?municipio=Rio%20de%20Janeiro&cnae=8630503"
curl "http://localhost:3000/empresas/search?municipio=6001&situacao=2&cnae=8610101&limit=100"
```

**Resposta 200:**
```json
{
  "page": 1,
  "limit": 20,
  "total": 42,
  "total_pages": 3,
  "resultados": [
    {
      "cnpj": "11222333000181",
      "cnpj_basico": "11222333",
      "razao_social": "...",
      "nome_fantasia": "...",
      "situacao_cadastral": 2,
      "situacao_cadastral_descricao": "Ativa",
      "uf": "RJ",
      "municipio": 6001,
      "municipio_descricao": "RIO DE JANEIRO",
      "cnae_fiscal_principal": 8630503,
      "cnae_fiscal_principal_descricao": "..."
    }
  ]
}
```

**400** — parâmetro numérico inválido (`situacao`/`cnae`/`page`/`limit` não é um código numérico),
ou município não encontrado/ambíguo.

## Módulos internos (não são endpoints)

- **`LookupsService`** — carrega as 6 tabelas de referência pequenas (`cnae`, `moti`, `munic`,
  `natju`, `pais`, `quals`) inteiras em memória na inicialização e resolve código → descrição sem
  precisar de `JOIN` no Postgres (necessário porque os tipos de coluna entre tabela de fato e
  tabela de referência nem sempre batem — ex: `cnae.codigo` é texto, `estabelecimento.pais` é
  texto mas `pais.codigo` é inteiro). Também resolve nome de município → código, tratando nomes
  duplicados entre UFs.
- **`rf-codes.ts`** — tabelas de código fixas que vêm do layout oficial da Receita Federal
  (situação cadastral, matriz/filial, porte, faixa etária, identificador de sócio) e não mudam
  com a carga do ETL, por isso ficam hardcoded em vez de tabela no banco.
- **`cpf-mask.ts`** — mascara CPF (`123.***.***-45`) sempre que um sócio é pessoa física; CNPJ de
  sócio pessoa jurídica passa sem alteração. Não é configurável.
