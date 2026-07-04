import { Global, Module } from '@nestjs/common';
import { Kysely, PostgresDialect } from 'kysely';
import { Pool } from 'pg';
import { Database } from './database.types';

export const KYSELY_CONNECTION = Symbol('KYSELY_CONNECTION');

@Global()
@Module({
  providers: [
    {
      provide: KYSELY_CONNECTION,
      useFactory: () =>
        new Kysely<Database>({
          dialect: new PostgresDialect({
            pool: new Pool({
              host: process.env.DB_HOST ?? 'db',
              port: Number(process.env.DB_PORT ?? 5432),
              user: process.env.DB_USER ?? 'postgres',
              password: process.env.DB_PASSWORD ?? 'postgres',
              database: process.env.DB_NAME ?? 'dados_rfb',
            }),
          }),
        }),
    },
  ],
  exports: [KYSELY_CONNECTION],
})
export class DatabaseModule {}
