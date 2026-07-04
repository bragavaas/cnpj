import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { DatabaseModule } from './database/database.module';
import { LookupsModule } from './lookups/lookups.module';
import { HealthController } from './health/health.controller';
import { CnpjModule } from './cnpj/cnpj.module';
import { EmpresasModule } from './empresas/empresas.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    DatabaseModule,
    LookupsModule,
    CnpjModule,
    EmpresasModule,
  ],
  controllers: [HealthController],
})
export class AppModule {}
