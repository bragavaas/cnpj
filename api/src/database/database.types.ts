/**
 * Tipos das tabelas criadas pelo ETL (pandas `to_sql`, sem PK/FK). Tipos confirmados via
 * `information_schema.columns` contra uma carga real (ver TASKS_DOCKER_API.md) - note que
 * `cnae.codigo` é texto e `estabelecimento.pais` também, ao contrário do que os nomes sugerem.
 */

export interface EmpresaTable {
  cnpj_basico: string;
  razao_social: string | null;
  natureza_juridica: number | null;
  qualificacao_responsavel: number | null;
  capital_social: number | null;
  porte_empresa: number | null;
  ente_federativo_responsavel: string | null;
}

export interface EstabelecimentoTable {
  cnpj_basico: string;
  cnpj_ordem: string;
  cnpj_dv: string;
  identificador_matriz_filial: number | null;
  nome_fantasia: string | null;
  situacao_cadastral: number | null;
  data_situacao_cadastral: number | null;
  motivo_situacao_cadastral: number | null;
  nome_cidade_exterior: string | null;
  pais: string | null;
  data_inicio_atividade: number | null;
  cnae_fiscal_principal: number | null;
  cnae_fiscal_secundaria: string | null;
  tipo_logradouro: string | null;
  logradouro: string | null;
  numero: string | null;
  complemento: string | null;
  bairro: string | null;
  cep: string | null;
  uf: string | null;
  municipio: number | null;
  ddd_1: string | null;
  telefone_1: string | null;
  ddd_2: string | null;
  telefone_2: string | null;
  ddd_fax: string | null;
  fax: string | null;
  correio_eletronico: string | null;
  situacao_especial: string | null;
  data_situacao_especial: number | null;
}

export interface SociosTable {
  cnpj_basico: string;
  identificador_socio: number | null;
  nome_socio_razao_social: string | null;
  cpf_cnpj_socio: string | null;
  qualificacao_socio: number | null;
  data_entrada_sociedade: number | null;
  pais: number | null;
  representante_legal: string | null;
  nome_do_representante: string | null;
  qualificacao_representante_legal: number | null;
  faixa_etaria: number | null;
}

export interface SimplesTable {
  cnpj_basico: string;
  opcao_pelo_simples: string | null;
  data_opcao_simples: number | null;
  data_exclusao_simples: number | null;
  opcao_mei: string | null;
  data_opcao_mei: number | null;
  data_exclusao_mei: number | null;
}

export interface CnaeTable {
  codigo: string;
  descricao: string | null;
}

export interface CodeDescriptionTable {
  codigo: number;
  descricao: string | null;
}

export interface Database {
  empresa: EmpresaTable;
  estabelecimento: EstabelecimentoTable;
  socios: SociosTable;
  simples: SimplesTable;
  cnae: CnaeTable;
  moti: CodeDescriptionTable;
  munic: CodeDescriptionTable;
  natju: CodeDescriptionTable;
  pais: CodeDescriptionTable;
  quals: CodeDescriptionTable;
}
