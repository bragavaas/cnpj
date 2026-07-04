import { Inject, Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { Kysely } from 'kysely';
import { KYSELY_CONNECTION } from '../database/database.module';
import { Database } from '../database/database.types';

type LookupTableName = 'cnae' | 'moti' | 'munic' | 'natju' | 'pais' | 'quals';

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
