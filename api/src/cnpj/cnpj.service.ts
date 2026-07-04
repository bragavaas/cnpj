import { BadRequestException, Inject, Injectable, NotFoundException } from '@nestjs/common';
import { Kysely } from 'kysely';
import { KYSELY_CONNECTION } from '../database/database.module';
import { Database } from '../database/database.types';
import { LookupsService } from '../lookups/lookups.service';
import { maskCpf } from '../common/cpf-mask';
import {
  FAIXA_ETARIA,
  IDENTIFICADOR_MATRIZ_FILIAL,
  IDENTIFICADOR_SOCIO,
  PORTE_EMPRESA,
  SITUACAO_CADASTRAL,
  lookupCode,
} from '../common/rf-codes';

@Injectable()
export class CnpjService {
  constructor(
    @Inject(KYSELY_CONNECTION) private readonly db: Kysely<Database>,
    private readonly lookups: LookupsService,
  ) {}

  async find(cnpjRaw: string, opts: { all: boolean }) {
    const digits = cnpjRaw.replace(/\D/g, '');
    if (digits.length !== 8 && digits.length !== 14) {
      throw new BadRequestException(
        'Informe um CNPJ com 8 dígitos (raiz, ex: 12345678) ou 14 dígitos (completo, ex: 12345678000190).',
      );
    }
    const cnpjBasico = digits.slice(0, 8);
    const cnpjOrdemFiltro = digits.length === 14 ? digits.slice(8, 12) : null;

    const [estabelecimentos, socios, simples] = await Promise.all([
      this.db
        .selectFrom('estabelecimento')
        // LEFT JOIN (não INNER): em tese todo estabelecimento tem uma empresa correspondente,
        // mas isso não é garantido por FK no banco (tabelas criadas pelo pandas, sem FK) - com
        // INNER, uma empresa "órfã" (ou uma carga parcial/de teste sem overlap de cnpj_basico
        // entre os dois arquivos) faria o endpoint inteiro voltar 404 mesmo com o estabelecimento
        // existindo.
        .leftJoin('empresa', 'empresa.cnpj_basico', 'estabelecimento.cnpj_basico')
        .selectAll('estabelecimento')
        .select([
          'empresa.razao_social',
          'empresa.natureza_juridica',
          'empresa.qualificacao_responsavel',
          'empresa.capital_social',
          'empresa.porte_empresa',
          'empresa.ente_federativo_responsavel',
        ])
        .where('estabelecimento.cnpj_basico', '=', cnpjBasico)
        .orderBy('estabelecimento.cnpj_ordem')
        .execute(),
      this.db.selectFrom('socios').selectAll().where('cnpj_basico', '=', cnpjBasico).execute(),
      this.db
        .selectFrom('simples')
        .selectAll()
        .where('cnpj_basico', '=', cnpjBasico)
        .executeTakeFirst(),
    ]);

    if (estabelecimentos.length === 0) {
      throw new NotFoundException('CNPJ não encontrado.');
    }

    const sociosResp = socios.map((s) => ({
      identificador_socio: s.identificador_socio,
      identificador_socio_descricao: lookupCode(IDENTIFICADOR_SOCIO, s.identificador_socio),
      nome: s.nome_socio_razao_social,
      cpf_cnpj: maskCpf(s.cpf_cnpj_socio),
      qualificacao: s.qualificacao_socio,
      qualificacao_descricao: this.lookups.resolveQualificacao(s.qualificacao_socio),
      data_entrada_sociedade: s.data_entrada_sociedade,
      pais: s.pais,
      pais_descricao: this.lookups.resolvePais(s.pais),
      representante_legal: s.representante_legal,
      nome_do_representante: s.nome_do_representante,
      qualificacao_representante_legal: s.qualificacao_representante_legal,
      qualificacao_representante_legal_descricao: this.lookups.resolveQualificacao(
        s.qualificacao_representante_legal,
      ),
      faixa_etaria: s.faixa_etaria,
      faixa_etaria_descricao: lookupCode(FAIXA_ETARIA, s.faixa_etaria),
    }));

    const simplesResp = simples
      ? {
          opcao_pelo_simples: simples.opcao_pelo_simples === 'S',
          data_opcao_simples: simples.data_opcao_simples,
          data_exclusao_simples: simples.data_exclusao_simples,
          opcao_mei: simples.opcao_mei === 'S',
          data_opcao_mei: simples.data_opcao_mei,
          data_exclusao_mei: simples.data_exclusao_mei,
        }
      : null;

    const estabelecimentosResp = estabelecimentos.map((e) => ({
      cnpj: e.cnpj_basico + e.cnpj_ordem + e.cnpj_dv,
      cnpj_basico: e.cnpj_basico,
      cnpj_ordem: e.cnpj_ordem,
      cnpj_dv: e.cnpj_dv,
      identificador_matriz_filial: e.identificador_matriz_filial,
      identificador_matriz_filial_descricao: lookupCode(
        IDENTIFICADOR_MATRIZ_FILIAL,
        e.identificador_matriz_filial,
      ),
      razao_social: e.razao_social,
      nome_fantasia: e.nome_fantasia,
      situacao_cadastral: e.situacao_cadastral,
      situacao_cadastral_descricao: lookupCode(SITUACAO_CADASTRAL, e.situacao_cadastral),
      data_situacao_cadastral: e.data_situacao_cadastral,
      motivo_situacao_cadastral: e.motivo_situacao_cadastral,
      motivo_situacao_cadastral_descricao: this.lookups.resolveMotivoSituacaoCadastral(
        e.motivo_situacao_cadastral,
      ),
      data_inicio_atividade: e.data_inicio_atividade,
      natureza_juridica: e.natureza_juridica,
      natureza_juridica_descricao: this.lookups.resolveNaturezaJuridica(e.natureza_juridica),
      qualificacao_responsavel: e.qualificacao_responsavel,
      qualificacao_responsavel_descricao: this.lookups.resolveQualificacao(
        e.qualificacao_responsavel,
      ),
      capital_social: e.capital_social,
      porte_empresa: e.porte_empresa,
      porte_empresa_descricao: lookupCode(PORTE_EMPRESA, e.porte_empresa),
      ente_federativo_responsavel: e.ente_federativo_responsavel,
      atividade_principal: {
        codigo: e.cnae_fiscal_principal,
        descricao: this.lookups.resolveCnae(e.cnae_fiscal_principal),
      },
      atividades_secundarias: this.lookups.resolveCnaeSecundarias(e.cnae_fiscal_secundaria),
      endereco: {
        tipo_logradouro: e.tipo_logradouro,
        logradouro: e.logradouro,
        numero: e.numero,
        complemento: e.complemento,
        bairro: e.bairro,
        cep: e.cep,
        uf: e.uf,
        municipio: e.municipio,
        municipio_descricao: this.lookups.resolveMunicipio(e.municipio),
        pais: e.pais,
        pais_descricao: this.lookups.resolvePais(e.pais),
        nome_cidade_exterior: e.nome_cidade_exterior,
      },
      contato: {
        ddd_1: e.ddd_1,
        telefone_1: e.telefone_1,
        ddd_2: e.ddd_2,
        telefone_2: e.telefone_2,
        ddd_fax: e.ddd_fax,
        fax: e.fax,
        email: e.correio_eletronico,
      },
      situacao_especial: e.situacao_especial,
      data_situacao_especial: e.data_situacao_especial,
    }));

    if (cnpjOrdemFiltro) {
      const encontrado = estabelecimentosResp.find((e) => e.cnpj_ordem === cnpjOrdemFiltro);
      if (!encontrado) {
        throw new NotFoundException('Estabelecimento não encontrado para esse CNPJ.');
      }
      return { ...encontrado, socios: sociosResp, simples: simplesResp };
    }

    if (opts.all) {
      return {
        cnpj_basico: cnpjBasico,
        razao_social: estabelecimentosResp[0].razao_social,
        total_estabelecimentos: estabelecimentosResp.length,
        estabelecimentos: estabelecimentosResp,
        socios: sociosResp,
        simples: simplesResp,
      };
    }

    // 8 dígitos sem "?all=true": matriz por padrão (prefere ordem "0001"; se não existir, o
    // primeiro estabelecimento disponível em ordem crescente de cnpj_ordem).
    const matriz =
      estabelecimentosResp.find((e) => e.cnpj_ordem === '0001') ?? estabelecimentosResp[0];
    return {
      ...matriz,
      total_estabelecimentos: estabelecimentosResp.length,
      socios: sociosResp,
      simples: simplesResp,
    };
  }
}
