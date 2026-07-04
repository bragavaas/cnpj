import { Controller, Get, Query } from '@nestjs/common';
import { ApiOperation, ApiQuery, ApiTags } from '@nestjs/swagger';
import { EmpresasService } from './empresas.service';

@ApiTags('empresas')
@Controller('empresas')
export class EmpresasController {
  constructor(private readonly empresasService: EmpresasService) {}

  @Get('search')
  @ApiOperation({ summary: 'Busca paginada de empresas por nome, UF, situação cadastral e CNAE' })
  @ApiQuery({ name: 'razao_social', required: false })
  @ApiQuery({ name: 'uf', required: false })
  @ApiQuery({ name: 'municipio', required: false, description: 'Código do município (tabela munic)' })
  @ApiQuery({ name: 'situacao', required: false, description: '1=Nula 2=Ativa 3=Suspensa 4=Inapta 8=Baixada' })
  @ApiQuery({ name: 'cnae', required: false, description: 'Código do CNAE fiscal principal' })
  @ApiQuery({ name: 'page', required: false, description: 'Padrão 1' })
  @ApiQuery({ name: 'limit', required: false, description: 'Padrão 20, máximo 100' })
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
      municipio: municipio !== undefined ? Number(municipio) : undefined,
      situacao: situacao !== undefined ? Number(situacao) : undefined,
      cnae: cnae !== undefined ? Number(cnae) : undefined,
      page: page !== undefined ? Number(page) : undefined,
      limit: limit !== undefined ? Number(limit) : undefined,
    });
  }
}
