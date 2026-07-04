/**
 * `socios.cpf_cnpj_socio` guarda CPF (pessoa física, 11 dígitos) ou CNPJ (pessoa jurídica sócia,
 * 14 dígitos) no mesmo campo. CPF é sempre mascarado antes de sair da API - não é configurável,
 * essa é uma ferramenta interna e não há motivo para expor CPF cru de terceiros.
 */
export function maskCpf(value: string | null | undefined): string | null {
  if (!value) return null;
  const digits = value.replace(/\D/g, '');
  if (digits.length !== 11) return value; // CNPJ de sócio pessoa jurídica: passa direto
  return `${digits.slice(0, 3)}.***.***-${digits.slice(9, 11)}`;
}
