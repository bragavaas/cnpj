import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableCors();

  const config = new DocumentBuilder()
    .setTitle('API de CNPJ - Receita Federal')
    .setDescription(
      'API somente-leitura sobre os dados públicos de CNPJ importados pelo ETL deste repo. ' +
        'Uso local/interno - sem autenticação, não exponha além de localhost/rede Docker.',
    )
    .setVersion('0.1.0')
    .build();
  const document = SwaggerModule.createDocument(app, config);
  SwaggerModule.setup('docs', app, document);

  const port = Number(process.env.PORT ?? 3000);
  await app.listen(port);
  console.log(`API de CNPJ rodando em http://localhost:${port} (docs em /docs)`);
}
bootstrap();
