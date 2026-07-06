import { BadRequestException, Controller, Get, Query } from '@nestjs/common';
import { ApiOperation, ApiQuery, ApiResponse, ApiTags } from '@nestjs/swagger';
import { EmpresasService } from './empresas.service';
import { LookupsService } from '../lookups/lookups.service';

/**
 * Query params chegam sempre como string. `Number(value)` em algo não numérico (ex: um nome de
 * cidade em vez do código, ou um CNAE formatado como "8630-5/01") vira NaN - sem essa validação,
 * o NaN seguia direto pro Postgres e virava um 500 opaco (`invalid input syntax for type integer:
 * "NaN"`) em vez de um 400 explicando o problema.
 */
function parseIntQuery(name: string, value: string | undefined): number | undefined {
  if (value === undefined) return undefined;
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) {
    throw new BadRequestException(`Parâmetro "${name}" deve ser um código numérico, recebido: "${value}".`);
  }
  return parsed;
}

/** Aceita o CNAE em qualquer formatação (ex: "8630-5/01") e mantém só os dígitos antes de
 * converter para o inteiro usado em `estabelecimento.cnae_fiscal_principal`. */
function sanitizeCnae(value: string | undefined): number | undefined {
  if (value === undefined) return undefined;
  const digits = value.replace(/\D/g, '');
  if (!digits) {
    throw new BadRequestException(`Parâmetro "cnae" não contém nenhum dígito, recebido: "${value}".`);
  }
  return Number(digits);
}

@ApiTags('empresas')
@Controller('empresas')
export class EmpresasController {
  constructor(
    private readonly empresasService: EmpresasService,
    private readonly lookups: LookupsService,
  ) {}

  @Get('search')
  @ApiOperation({ summary: 'Busca paginada de empresas por nome, UF, situação cadastral e CNAE' })
  @ApiQuery({ name: 'razao_social', required: false })
  @ApiQuery({ name: 'uf', required: false })
  @ApiQuery({
    name: 'municipio',
    required: false,
    description: 'Nome (ex: "Rio de Janeiro") ou código (tabela munic) do município',
  })
  @ApiQuery({ name: 'situacao', required: false, description: '1=Nula 2=Ativa 3=Suspensa 4=Inapta 8=Baixada' })
  @ApiQuery({
    name: 'cnae',
    required: false,
    description: 'Código do CNAE fiscal principal, com ou sem formatação (ex: "8630501" ou "8630-5/01")',
  })
  @ApiQuery({ name: 'page', required: false, description: 'Padrão 1' })
  @ApiQuery({ name: 'limit', required: false, description: 'Padrão 20, máximo 100' })
  @ApiResponse({ status: 200, description: 'Lista paginada de resultados (pode vir vazia)' })
  @ApiResponse({
    status: 400,
    description:
      'Parâmetro numérico inválido (situacao/cnae/page/limit), ou município não encontrado/ambíguo',
  })
  search(
    @Query('razao_social') razaoSocial?: string,
    @Query('uf') uf?: string,
    @Query('municipio') municipio?: string,
    @Query('situacao') situacao?: string,
    @Query('cnae') cnae?: string,
    @Query('page') page?: string,
    @Query('limit') limit?: string,
  ) {
    return this.empresasService.search({
      razao_social: razaoSocial,
      uf,
      municipio: this.resolveMunicipio(municipio),
      situacao: parseIntQuery('situacao', situacao),
      cnae: sanitizeCnae(cnae),
      page: parseIntQuery('page', page),
      limit: parseIntQuery('limit', limit),
    });
  }

  /** Aceita tanto o código numérico direto quanto o nome do município (ex: "Rio de Janeiro"),
   * traduzindo o nome via `LookupsService`. Nomes de município não são únicos no Brasil (ex:
   * "Bom Jesus" existe em 5 estados), então um nome ambíguo vira 400 pedindo o código em vez de
   * adivinhar qual cidade o usuário quis dizer. */
  private resolveMunicipio(value: string | undefined): number | undefined {
    if (value === undefined) return undefined;
    const trimmed = value.trim();
    if (/^\d+$/.test(trimmed)) {
      return Number(trimmed);
    }
    const codigos = this.lookups.findMunicipioCodigosPorNome(trimmed);
    if (codigos.length === 0) {
      throw new BadRequestException(
        `Município não encontrado: "${value}". Informe o nome exato (tabela munic da Receita Federal) ou o código numérico.`,
      );
    }
    if (codigos.length > 1) {
      throw new BadRequestException(
        `"${value}" é ambíguo: existem ${codigos.length} municípios com esse nome em estados diferentes. ` +
          `Informe o código numérico (um de: ${codigos.join(', ')}).`,
      );
    }
    return codigos[0];
  }
}
