import { Controller, Get, Param, Query } from '@nestjs/common';
import { ApiOperation, ApiParam, ApiQuery, ApiResponse, ApiTags } from '@nestjs/swagger';
import { CnpjService } from './cnpj.service';

@ApiTags('cnpj')
@Controller('cnpj')
export class CnpjController {
  constructor(private readonly cnpjService: CnpjService) {}

  @Get(':cnpj')
  @ApiOperation({
    summary: 'Consulta um CNPJ (8 dígitos = raiz/matriz, 14 dígitos = estabelecimento específico)',
    description:
      'Resposta consolidada com dados cadastrais, endereço, sócios (CPF sempre mascarado) e ' +
      'situação no Simples/MEI, com os códigos da Receita já traduzidos.',
  })
  @ApiParam({
    name: 'cnpj',
    description: 'CNPJ com 8 dígitos (raiz) ou 14 dígitos (completo), com ou sem formatação',
    example: '11222333000181',
  })
  @ApiQuery({
    name: 'all',
    required: false,
    description: 'Com 8 dígitos, retorna todos os estabelecimentos da raiz em vez de só a matriz',
  })
  @ApiResponse({ status: 200, description: 'CNPJ encontrado' })
  @ApiResponse({ status: 400, description: 'CNPJ com quantidade de dígitos inválida (nem 8 nem 14)' })
  @ApiResponse({ status: 404, description: 'CNPJ (ou estabelecimento específico) não encontrado' })
  find(@Param('cnpj') cnpj: string, @Query('all') all?: string) {
    return this.cnpjService.find(cnpj, { all: all === 'true' });
  }
}
