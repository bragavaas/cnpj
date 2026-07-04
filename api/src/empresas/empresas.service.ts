import { Inject, Injectable } from '@nestjs/common';
import { Kysely, sql } from 'kysely';
import { KYSELY_CONNECTION } from '../database/database.module';
import { Database } from '../database/database.types';
import { LookupsService } from '../lookups/lookups.service';
import { SITUACAO_CADASTRAL, lookupCode } from '../common/rf-codes';

export interface EmpresasSearchParams {
  razao_social?: string;
  uf?: string;
  municipio?: number;
  situacao?: number;
  cnae?: number;
  page?: number;
  limit?: number;
}

@Injectable()
export class EmpresasService {
  constructor(
    @Inject(KYSELY_CONNECTION) private readonly db: Kysely<Database>,
    private readonly lookups: LookupsService,
  ) {}

  async search(params: EmpresasSearchParams) {
    const page = Math.max(1, params.page ?? 1);
    const limit = Math.min(100, Math.max(1, params.limit ?? 20));
    const offset = (page - 1) * limit;

    const query = this.db
      .selectFrom('estabelecimento')
      .innerJoin('empresa', 'empresa.cnpj_basico', 'estabelecimento.cnpj_basico')
      .select([
        'estabelecimento.cnpj_basico',
        'estabelecimento.cnpj_ordem',
        'estabelecimento.cnpj_dv',
        'estabelecimento.nome_fantasia',
        'estabelecimento.situacao_cadastral',
        'estabelecimento.uf',
        'estabelecimento.municipio',
        'estabelecimento.cnae_fiscal_principal',
        'empresa.razao_social',
      ])
      .select(sql<string>`count(*) over()`.as('total_count'))
      .$if(!!params.razao_social, (qb) =>
        qb.where('empresa.razao_social', 'ilike', `%${params.razao_social}%`),
      )
      .$if(!!params.uf, (qb) => qb.where('estabelecimento.uf', '=', params.uf!.toUpperCase()))
      .$if(params.municipio !== undefined, (qb) =>
        qb.where('estabelecimento.municipio', '=', params.municipio!),
      )
      .$if(params.situacao !== undefined, (qb) =>
        qb.where('estabelecimento.situacao_cadastral', '=', params.situacao!),
      )
      .$if(params.cnae !== undefined, (qb) =>
        qb.where('estabelecimento.cnae_fiscal_principal', '=', params.cnae!),
      )
      .orderBy('empresa.razao_social')
      .limit(limit)
      .offset(offset);

    const rows = await query.execute();
    const total = rows.length > 0 ? Number(rows[0].total_count) : 0;

    return {
      page,
      limit,
      total,
      total_pages: total > 0 ? Math.ceil(total / limit) : 0,
      resultados: rows.map((r) => ({
        cnpj: r.cnpj_basico + r.cnpj_ordem + r.cnpj_dv,
        cnpj_basico: r.cnpj_basico,
        razao_social: r.razao_social,
        nome_fantasia: r.nome_fantasia,
        situacao_cadastral: r.situacao_cadastral,
        situacao_cadastral_descricao: lookupCode(SITUACAO_CADASTRAL, r.situacao_cadastral),
        uf: r.uf,
        municipio: r.municipio,
        municipio_descricao: this.lookups.resolveMunicipio(r.municipio),
        cnae_fiscal_principal: r.cnae_fiscal_principal,
        cnae_fiscal_principal_descricao: this.lookups.resolveCnae(r.cnae_fiscal_principal),
      })),
    };
  }
}
