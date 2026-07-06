import { Controller, Get, Inject } from '@nestjs/common';
import { ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import { Kysely, sql } from 'kysely';
import { KYSELY_CONNECTION } from '../database/database.module';
import { Database } from '../database/database.types';

@ApiTags('health')
@Controller('health')
export class HealthController {
  constructor(@Inject(KYSELY_CONNECTION) private readonly db: Kysely<Database>) {}

  @Get()
  @ApiOperation({ summary: 'Checagem simples de saúde (inclui teste de conexão com o banco)' })
  @ApiResponse({ status: 200, description: '{ status: "ok"|"error", db: boolean }' })
  async check() {
    try {
      await sql`select 1`.execute(this.db);
      return { status: 'ok', db: true };
    } catch {
      return { status: 'error', db: false };
    }
  }
}
