import { Controller, Get, Param, Query } from '@nestjs/common';
import { ApiOperation, ApiQuery, ApiTags } from '@nestjs/swagger';
import { CnpjService } from './cnpj.service';

@ApiTags('cnpj')
@Controller('cnpj')
export class CnpjController {
  constructor(private readonly cnpjService: CnpjService) {}

  @Get(':cnpj')
  @ApiOperation({
    summary: 'Consulta um CNPJ (8 dígitos = raiz/matriz, 14 dígitos = estabelecimento específico)',
  })
  @ApiQuery({
    name: 'all',
    required: false,
    description: 'Com 8 dígitos, retorna todos os estabelecimentos da raiz em vez de só a matriz',
  })
  find(@Param('cnpj') cnpj: string, @Query('all') all?: string) {
    return this.cnpjService.find(cnpj, { all: all === 'true' });
  }
}
