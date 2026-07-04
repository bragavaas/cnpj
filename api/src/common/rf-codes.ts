/**
 * Mapas fixos de código -> descrição definidos no layout dos dados abertos de CNPJ da Receita
 * Federal (NOVOLAYOUTDOSDADOSABERTOSDOCNPJ.pdf, na raiz do repo). Não mudam com a carga do ETL,
 * por isso ficam em código em vez de tabelas no banco.
 */

export const SITUACAO_CADASTRAL: Record<string, string> = {
  '1': 'Nula',
  '2': 'Ativa',
  '3': 'Suspensa',
  '4': 'Inapta',
  '8': 'Baixada',
};

export const IDENTIFICADOR_MATRIZ_FILIAL: Record<string, string> = {
  '1': 'Matriz',
  '2': 'Filial',
};

export const PORTE_EMPRESA: Record<string, string> = {
  '0': 'Não informado',
  '1': 'Micro empresa',
  '3': 'Empresa de pequeno porte',
  '5': 'Demais',
};

export const FAIXA_ETARIA: Record<string, string> = {
  '0': 'Não se aplica',
  '1': '0 a 12 anos',
  '2': '13 a 20 anos',
  '3': '21 a 30 anos',
  '4': '31 a 40 anos',
  '5': '41 a 50 anos',
  '6': '51 a 60 anos',
  '7': '61 a 70 anos',
  '8': '71 a 80 anos',
  '9': 'Maior que 80 anos',
};

export const IDENTIFICADOR_SOCIO: Record<string, string> = {
  '1': 'Pessoa Jurídica',
  '2': 'Pessoa Física',
  '3': 'Estrangeiro',
};

/** Resolve um código fixo para sua descrição; retorna null se o código não bater com nada. */
export function lookupCode(
  map: Record<string, string>,
  code: number | string | null | undefined,
): string | null {
  if (code === null || code === undefined) return null;
  return map[String(code).trim()] ?? null;
}
