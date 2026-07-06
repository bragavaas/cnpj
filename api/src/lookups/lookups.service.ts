import { Inject, Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { Kysely } from 'kysely';
import { KYSELY_CONNECTION } from '../database/database.module';
import { Database } from '../database/database.types';

type LookupTableName = 'cnae' | 'moti' | 'munic' | 'natju' | 'pais' | 'quals';

/** Maiúsculas e sem acento, para comparar nome de município digitado pelo usuário com a
 * descrição da tabela `munic` independente de acentuação/caixa. */
const COMBINING_DIACRITICS = new RegExp('[\\u0300-\\u036f]', 'g');
function normalizeNome(value: string): string {
  return value
    .normalize('NFD')
    .replace(COMBINING_DIACRITICS, '')
    .trim()
    .toUpperCase();
}

/**
 * Carrega as 6 tabelas de referência (pequenas) inteiras em memória e resolve descrições em
 * código, normalizando o código para string dos dois lados. Isso evita ter que fazer JOIN no
 * Postgres entre colunas de tipos incompatíveis - `cnae.codigo` é texto enquanto
 * `estabelecimento.cnae_fiscal_principal` é inteiro, e `estabelecimento.pais` é texto enquanto
 * `pais.codigo` é inteiro (confirmado com uma carga real, ver TASKS_DOCKER_API.md).
 */
@Injectable()
export class LookupsService implements OnModuleInit {
  private readonly logger = new Logger(LookupsService.name);
  private readonly maps: Record<LookupTableName, Map<string, string>> = {
    cnae: new Map(),
    moti: new Map(),
    munic: new Map(),
    natju: new Map(),
    pais: new Map(),
    quals: new Map(),
  };
  /** nome de município normalizado -> código(s) - lista porque nomes de município se repetem
   * entre estados diferentes (ex: "Bom Jesus" existe em 5 UFs na tabela `munic`). */
  private municipioPorNome = new Map<string, number[]>();

  constructor(@Inject(KYSELY_CONNECTION) private readonly db: Kysely<Database>) {}

  async onModuleInit() {
    await this.refresh();
  }

  async refresh() {
    const tables: LookupTableName[] = ['cnae', 'moti', 'munic', 'natju', 'pais', 'quals'];
    const results = await Promise.all(
      tables.map((table) => this.db.selectFrom(table).selectAll().execute()),
    );
    tables.forEach((table, i) => {
      const map = new Map<string, string>();
      for (const row of results[i]) {
        if (row.codigo === null || row.codigo === undefined) continue;
        map.set(String(row.codigo).trim(), row.descricao ?? '');
      }
      this.maps[table] = map;
    });

    const municipioPorNome = new Map<string, number[]>();
    for (const [codigo, descricao] of this.maps.munic.entries()) {
      const normalizado = normalizeNome(descricao);
      if (!normalizado) continue;
      const codigos = municipioPorNome.get(normalizado) ?? [];
      codigos.push(Number(codigo));
      municipioPorNome.set(normalizado, codigos);
    }
    this.municipioPorNome = municipioPorNome;

    this.logger.log(
      'Lookups carregados: ' +
        tables.map((table) => `${table}=${this.maps[table].size}`).join(', '),
    );
  }

  private resolve(table: LookupTableName, code: string | number | null | undefined): string | null {
    if (code === null || code === undefined) return null;
    return this.maps[table].get(String(code).trim()) ?? null;
  }

  resolveCnae(codigo: string | number | null | undefined) {
    return this.resolve('cnae', codigo);
  }

  resolveMotivoSituacaoCadastral(codigo: string | number | null | undefined) {
    return this.resolve('moti', codigo);
  }

  resolveMunicipio(codigo: string | number | null | undefined) {
    return this.resolve('munic', codigo);
  }

  /** Traduz um nome de município (ex: "Rio de Janeiro") para o(s) código(s) da tabela `munic`.
   * Retorna uma lista vazia se não encontrar, e pode retornar mais de um código quando o nome é
   * ambíguo entre estados. */
  findMunicipioCodigosPorNome(nome: string): number[] {
    return this.municipioPorNome.get(normalizeNome(nome)) ?? [];
  }

  resolveNaturezaJuridica(codigo: string | number | null | undefined) {
    return this.resolve('natju', codigo);
  }

  resolvePais(codigo: string | number | null | undefined) {
    return this.resolve('pais', codigo);
  }

  resolveQualificacao(codigo: string | number | null | undefined) {
    return this.resolve('quals', codigo);
  }

  /**
   * `cnae_fiscal_secundaria` vem como uma string com códigos separados por vírgula. Resolve
   * todos numa passada, descartando entradas vazias.
   */
  resolveCnaeSecundarias(cnaeFiscalSecundaria: string | null | undefined) {
    if (!cnaeFiscalSecundaria) return [];
    return cnaeFiscalSecundaria
      .split(',')
      .map((codigo) => codigo.trim())
      .filter((codigo) => codigo.length > 0)
      .map((codigo) => ({ codigo, descricao: this.resolveCnae(codigo) }));
  }
}
