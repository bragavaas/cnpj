import datetime
import gc
import pathlib
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
import ftplib
import gzip
import os
import pandas as pd
import psycopg2
import re
import sys
import time
import requests
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile


def check_diff(url, file_name):
    '''
    Verifica se o arquivo no servidor existe no disco e se ele tem o mesmo
    tamanho no servidor.
    '''
    if not os.path.isfile(file_name):
        return True # ainda nao foi baixado

    response = requests.head(url, auth=RF_AUTH)
    new_size = int(response.headers.get('content-length', 0))
    old_size = os.path.getsize(file_name)
    if new_size != old_size:
        os.remove(file_name)
        return True # tamanho diferentes

    return False # arquivos sao iguais


#%%
def makedirs(path):
    '''
    cria path caso seja necessario
    '''
    if not os.path.exists(path):
        os.makedirs(path)

#%%
def to_sql(dataframe, **kwargs):
    '''
    Quebra em pedacos a tarefa de inserir registros no banco
    '''
    size = 4096  #TODO param
    total = len(dataframe)
    name = kwargs.get('name')

    def chunker(df):
        return (df[i:i + size] for i in range(0, len(df), size))

    for i, df in enumerate(chunker(dataframe)):
        df.to_sql(**kwargs)
        index = i * size
        percent = (index * 100) / total
        progress = f'{name} {percent:.2f}% {index:0{len(str(total))}}/{total}'
        sys.stdout.write(f'\r{progress}')
    sys.stdout.write('\n')

#%%
# Ler arquivo de configuração de ambiente # https://dev.to/jakewitcher/using-env-files-for-environment-variables-in-python-applications-55a1
def getEnv(env):
    return os.getenv(env)


current_path = pathlib.Path().resolve()
dotenv_path = os.path.join(current_path, '.env')
if not os.path.isfile(dotenv_path) and sys.stdin.isatty():
    print('Especifique o local do seu arquivo de configuração ".env". Por exemplo: C:\...\Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ\code')
    # C:\Aphonso_C\Git\Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ\code
    local_env = input()
    dotenv_path = os.path.join(local_env, '.env')
print(dotenv_path)
load_dotenv(dotenv_path=dotenv_path)

# Em ambientes não-interativos (ex: container Docker) não há como pedir o caminho do ".env" via
# input(), então validamos aqui que as variáveis obrigatórias já vieram do ambiente (.env ou
# "environment:" do docker-compose) e falhamos rápido com uma mensagem clara, em vez de seguir
# com valores None que só explodiriam de forma confusa mais adiante.
REQUIRED_ENV_VARS = ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'OUTPUT_FILES_PATH', 'EXTRACTED_FILES_PATH']
missing_env_vars = [var for var in REQUIRED_ENV_VARS if not getEnv(var)]
if missing_env_vars:
    sys.exit('Variáveis de ambiente faltando: ' + ', '.join(missing_env_vars) + '. Verifique seu arquivo ".env".')

# A partir de jan/2026 a Receita Federal passou a hospedar os dados abertos de CNPJ num
# compartilhamento público do Nextcloud (arquivos.receitafederal.gov.br), organizado em pastas
# "AAAA-MM" (uma por mês de referência), acessível via WebDAV com o token do link como usuário
# HTTP Basic e senha vazia. A raspagem de HTML antiga (Apache directory listing simples) não
# existe mais nesse endereço. Token descoberto via a página oficial de dados abertos
# (dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj) e validado
# manualmente; se a Receita Federal trocar o link de novo, sobrescreva via env var
# ETL_RF_SHARE_TOKEN sem precisar mexer no código.
RF_WEBDAV_BASE = 'https://arquivos.receitafederal.gov.br/public.php/webdav/'
RF_SHARE_TOKEN = getEnv('ETL_RF_SHARE_TOKEN') or 'YggdBLfdninEJX9'
RF_AUTH = (RF_SHARE_TOKEN, '')

#%%
# Read details from ".env" file:
output_files = getEnv('OUTPUT_FILES_PATH')
makedirs(output_files)

extracted_files = getEnv('EXTRACTED_FILES_PATH')
makedirs(extracted_files)

print('Diretórios definidos: \n' +
      'output_files: ' + str(output_files)  + '\n' +
      'extracted_files: ' + str(extracted_files))

#%%
def webdav_list(path):
    '''
    Lista os nomes dos itens dentro de uma pasta do compartilhamento público WebDAV da Receita
    Federal (sem incluir a própria pasta consultada).
    '''
    response = requests.request('PROPFIND', RF_WEBDAV_BASE + path, auth=RF_AUTH, headers={'Depth': '1'})
    response.raise_for_status()
    tree = ET.fromstring(response.content)
    hrefs = [el.text for el in tree.findall('.//{DAV:}href') if el.text]
    self_name = path.rstrip('/').rsplit('/', 1)[-1] if path else ''
    names = [urllib.parse.unquote(href.rstrip('/').rsplit('/', 1)[-1]) for href in hrefs]
    return [name for name in names if name and name != self_name]

# Pastas de referência mensal disponíveis (formato "AAAA-MM") - pegamos sempre a mais recente.
meses_disponiveis = sorted(m for m in webdav_list('') if re.fullmatch(r'\d{4}-\d{2}', m))
if not meses_disponiveis:
    sys.exit('Não foi possível encontrar nenhuma pasta de referência mensal no compartilhamento da Receita Federal.')
mes_mais_recente = meses_disponiveis[-1]
print('Mês de referência mais recente disponível na Receita Federal: ' + mes_mais_recente)

dados_rf = RF_WEBDAV_BASE + mes_mais_recente + '/'
Files = [f for f in webdav_list(mes_mais_recente + '/') if f.lower().endswith('.zip')]

#%%
# Modo de teste: permite baixar/processar só uma fração dos arquivos e das linhas, para validar
# o pipeline rapidamente (ex: rodando em Docker antes de disparar a carga completa, que leva
# horas). Quando ETL_TEST_MODE não está setado, o comportamento é 100% o mesmo de sempre (carga
# completa, sem limites).
ETL_TEST_MODE = (getEnv('ETL_TEST_MODE') or '').lower() == 'true'
ETL_MAX_FILES_PER_TYPE = int(getEnv('ETL_MAX_FILES_PER_TYPE') or 0) or None
# Só vale fora do modo de teste se ETL_TEST_MODE também estiver true - senão um ETL_MAX_ROWS
# esquecido no ".env" de uma rodada de teste anterior faria a carga completa truncar empresa e
# socios silenciosamente (o "nrows=" desses dois é aplicado direto, sem checar ETL_TEST_MODE).
ETL_MAX_ROWS = (int(getEnv('ETL_MAX_ROWS') or 0) or None) if ETL_TEST_MODE else None

# Filtro de carga parcial (opcional). Quando ETL_FILTER_UF, ETL_FILTER_MUNICIPIO ou ETL_FILTER_CNAE_FILE
# estão definidos, só os estabelecimentos que passam no filtro entram no banco, e as tabelas empresa e
# simples recebem só os cnpj_basico desses estabelecimentos. As tabelas de referência (cnae, munic, natju,
# moti, pais, quals) continuam completas. Sem nenhuma dessas variáveis, o comportamento é o de sempre.
#   ETL_FILTER_UF            ex.: RJ (uma UF; comparação exata com a coluna uf)
#   ETL_FILTER_MUNICIPIO     ex.: 6001 (código de município da Receita, tabela munic; lista separada por vírgula)
#   ETL_FILTER_CNAE_FILE     caminho de um CSV com a coluna "codigo" (7 dígitos, com ou sem formatação);
#                            filtra pela atividade principal (cnae_fiscal_principal)
#   ETL_SKIP_SOCIOS          true para não carregar a tabela de sócios (dados pessoais que nem todo uso precisa)
ETL_FILTER_UF = (getEnv('ETL_FILTER_UF') or '').strip().upper() or None
ETL_FILTER_MUNICIPIO = set(m.strip() for m in (getEnv('ETL_FILTER_MUNICIPIO') or '').split(',') if m.strip()) or None
ETL_FILTER_CNAE_FILE = getEnv('ETL_FILTER_CNAE_FILE') or None
ETL_SKIP_SOCIOS = (getEnv('ETL_SKIP_SOCIOS') or '').lower() == 'true'
ETL_FILTER_CNAES = None
if ETL_FILTER_CNAE_FILE:
    _cnae_df = pd.read_csv(ETL_FILTER_CNAE_FILE, dtype=str)
    _col = 'codigo' if 'codigo' in _cnae_df.columns else _cnae_df.columns[0]
    ETL_FILTER_CNAES = set(re.sub(r'\D', '', str(c)).zfill(7) for c in _cnae_df[_col].dropna())
    print('Filtro de CNAE: ' + str(len(ETL_FILTER_CNAES)) + ' códigos lidos de ' + ETL_FILTER_CNAE_FILE)
FILTRO_ATIVO = bool(ETL_FILTER_UF or ETL_FILTER_MUNICIPIO or ETL_FILTER_CNAES)
if FILTRO_ATIVO:
    print('Carga parcial ativa: uf=' + str(ETL_FILTER_UF) + ' municipio=' + str(ETL_FILTER_MUNICIPIO) +
          ' cnaes=' + (str(len(ETL_FILTER_CNAES)) if ETL_FILTER_CNAES else 'todos'))
# cnpj_basico dos estabelecimentos que passaram no filtro; preenchido no bloco de estabelecimento e usado
# para filtrar empresa e simples. Por isso o bloco de estabelecimento roda antes do de empresa.
cnpj_basico_filtrados = set()

def filtrar_estabelecimento(df):
    if not FILTRO_ATIVO:
        return df
    mask = pd.Series(True, index=df.index)
    if ETL_FILTER_UF:
        mask &= df['uf'].astype(str).str.upper() == ETL_FILTER_UF
    if ETL_FILTER_MUNICIPIO:
        mask &= df['municipio'].astype(str).isin(ETL_FILTER_MUNICIPIO)
    if ETL_FILTER_CNAES:
        mask &= df['cnae_fiscal_principal'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(7).isin(ETL_FILTER_CNAES)
    return df[mask]

def limit_files_per_type(files, max_per_type):
    '''
    Mantém só os N primeiros arquivos de cada categoria "fracionada" (empresa/estabelecimento/
    socios/simples, que vêm divididos em várias partes). As tabelas de referência (cnae, moti,
    munic, natju, pais, quals) nunca são limitadas aqui: são pequenas e o resto do script espera
    tê-las completas.
    '''
    if not max_per_type:
        return files
    fractioned_keywords = ['EMPRE', 'ESTABELE', 'SOCIO', 'SIMPLES']
    counts = {kw: 0 for kw in fractioned_keywords}
    limited = []
    for f in files:
        matched_keyword = next((kw for kw in fractioned_keywords if kw in f.upper()), None)
        if matched_keyword is None:
            limited.append(f)
            continue
        if counts[matched_keyword] < max_per_type:
            limited.append(f)
            counts[matched_keyword] += 1
    return limited

if ETL_TEST_MODE:
    Files = limit_files_per_type(Files, ETL_MAX_FILES_PER_TYPE)
    print('ETL_TEST_MODE ativo: limitado a ' + str(ETL_MAX_FILES_PER_TYPE) +
          ' arquivo(s) por categoria e ' + str(ETL_MAX_ROWS) + ' linha(s) por arquivo.')

print('Arquivos que serão baixados:')
i_f = 0
for f in Files:
    i_f += 1
    print(str(i_f) + ' - ' + f)

#%%
########################################################################################################################
## DOWNLOAD ############################################################################################################
########################################################################################################################
def bar_progress(current, total, width=80):
  progress_message = "Downloading: %d%% [%d / %d] bytes - " % (current / total * 100, current, total)
  # Don't use print() as it will print in new line every time.
  sys.stdout.write("\r" + progress_message)
  sys.stdout.flush()

def download_file(url, output_dir, auth=None):
    '''
    Baixa um arquivo autenticado (HTTP Basic) em streaming, salvando em output_dir com o mesmo
    nome do final da URL. Substitui o antigo wget.download, que não suporta autenticação e não
    funciona mais desde que a Receita Federal passou a exigir o token do compartilhamento.
    '''
    local_filename = os.path.join(output_dir, url.rstrip('/').rsplit('/', 1)[-1])
    with requests.get(url, auth=auth, stream=True, timeout=60) as response:
        response.raise_for_status()
        total = int(response.headers.get('content-length', 0))
        downloaded = 0
        with open(local_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    bar_progress(downloaded, total)
    sys.stdout.write('\n')
    return local_filename

#%%
# Download arquivos ################################################################################################################################
i_l = 0
for l in Files:
    # Download dos arquivos
    i_l += 1
    print('Baixando arquivo:')
    print(str(i_l) + ' - ' + l)
    url = dados_rf+l
    file_name = os.path.join(output_files, l)
    if check_diff(url, file_name):
        download_file(url, output_files, auth=RF_AUTH)

####################################################################################################################################################

#%%
# Extracting files:
i_l = 0
for l in Files:
    try:
        i_l += 1
        print('Descompactando arquivo:')
        print(str(i_l) + ' - ' + l)
        full_path = os.path.join(output_files, l)
        with zipfile.ZipFile(full_path, 'r') as zip_ref:
            zip_ref.extractall(extracted_files)
    except:
        pass

#%%
########################################################################################################################
## LER E INSERIR DADOS #################################################################################################
########################################################################################################################
insert_start = time.time()

# Files:
Items = [name for name in os.listdir(extracted_files) if name.endswith('')]

# Separar arquivos:
arquivos_empresa = []
arquivos_estabelecimento = []
arquivos_socios = []
arquivos_simples = []
arquivos_cnae = []
arquivos_moti = []
arquivos_munic = []
arquivos_natju = []
arquivos_pais = []
arquivos_quals = []
for i in range(len(Items)):
    if Items[i].find('EMPRE') > -1:
        arquivos_empresa.append(Items[i])
    elif Items[i].find('ESTABELE') > -1:
        arquivos_estabelecimento.append(Items[i])
    elif Items[i].find('SOCIO') > -1:
        arquivos_socios.append(Items[i])
    elif Items[i].find('SIMPLES') > -1:
        arquivos_simples.append(Items[i])
    elif Items[i].find('CNAE') > -1:
        arquivos_cnae.append(Items[i])
    elif Items[i].find('MOTI') > -1:
        arquivos_moti.append(Items[i])
    elif Items[i].find('MUNIC') > -1:
        arquivos_munic.append(Items[i])
    elif Items[i].find('NATJU') > -1:
        arquivos_natju.append(Items[i])
    elif Items[i].find('PAIS') > -1:
        arquivos_pais.append(Items[i])
    elif Items[i].find('QUALS') > -1:
        arquivos_quals.append(Items[i])
    else:
        pass

#%%
# Conectar no banco de dados:
# Dados da conexão com o BD
user=getEnv('DB_USER')
passw=getEnv('DB_PASSWORD')
host=getEnv('DB_HOST')
port=getEnv('DB_PORT')
database=getEnv('DB_NAME')

# Conectar:
# Usar URL.create / kwargs (em vez de concatenar strings) evita que senhas com caracteres
# especiais (@, :, /, %, espaço) corrompam a connection string ou façam a conexão falhar
# silenciosamente com credenciais erradas.
engine = create_engine(URL.create(
    'postgresql',
    username=user,
    password=passw,
    host=host,
    port=int(port),
    database=database,
))
conn = psycopg2.connect(dbname=database, user=user, host=host, port=port, password=passw)
cur = conn.cursor()

#%%
# Arquivos de estabelecimento:
estabelecimento_insert_start = time.time()
print("""
###############################
## Arquivos de ESTABELECIMENTO:
###############################
""")

# Drop table antes do insert
cur.execute('DROP TABLE IF EXISTS "estabelecimento";')
conn.commit()

print('Tem %i arquivos de estabelecimento!' % len(arquivos_estabelecimento))
for e in range(0, len(arquivos_estabelecimento)):
    print('Trabalhando no arquivo: '+arquivos_estabelecimento[e]+' [...]')
    try:
        del estabelecimento
        gc.collect()
    except:
        pass

    # estabelecimento = pd.DataFrame(columns=[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28])
    estabelecimento_dtypes = {0: object, 1: object, 2: object, 3: 'Int32', 4: object, 5: 'Int32', 6: 'Int32',
                              7: 'Int32', 8: object, 9: object, 10: 'Int32', 11: 'Int32', 12: object, 13: object,
                              14: object, 15: object, 16: object, 17: object, 18: object, 19: object,
                              20: 'Int32', 21: object, 22: object, 23: object, 24: object, 25: object,
                              26: object, 27: object, 28: object, 29: 'Int32'}
    extracted_file_path = os.path.join(extracted_files, arquivos_estabelecimento[e])

    NROWS = ETL_MAX_ROWS or 2000000
    part = 0
    while True:
        estabelecimento = pd.read_csv(filepath_or_buffer=extracted_file_path,
                              sep=';',
                              nrows=NROWS,
                              skiprows=NROWS * part,
                              header=None,
                              dtype=estabelecimento_dtypes,
                              encoding='latin-1',
        )

        linhas_lidas = len(estabelecimento)
        # Tratamento do arquivo antes de inserir na base:
        estabelecimento = estabelecimento.reset_index()
        del estabelecimento['index']
        gc.collect()

        # Renomear colunas
        estabelecimento.columns = ['cnpj_basico',
                                   'cnpj_ordem',
                                   'cnpj_dv',
                                   'identificador_matriz_filial',
                                   'nome_fantasia',
                                   'situacao_cadastral',
                                   'data_situacao_cadastral',
                                   'motivo_situacao_cadastral',
                                   'nome_cidade_exterior',
                                   'pais',
                                   'data_inicio_atividade',
                                   'cnae_fiscal_principal',
                                   'cnae_fiscal_secundaria',
                                   'tipo_logradouro',
                                   'logradouro',
                                   'numero',
                                   'complemento',
                                   'bairro',
                                   'cep',
                                   'uf',
                                   'municipio',
                                   'ddd_1',
                                   'telefone_1',
                                   'ddd_2',
                                   'telefone_2',
                                   'ddd_fax',
                                   'fax',
                                   'correio_eletronico',
                                   'situacao_especial',
                                   'data_situacao_especial']

        # Carga parcial: fica só o que passa no filtro; guarda os cnpj_basico para empresa e simples
        estabelecimento = filtrar_estabelecimento(estabelecimento)
        if FILTRO_ATIVO:
            cnpj_basico_filtrados.update(estabelecimento['cnpj_basico'].astype(str).tolist())
            print('Linhas após o filtro: ' + str(len(estabelecimento)) + ' (acumulado de cnpj_basico: ' + str(len(cnpj_basico_filtrados)) + ')')
        # Gravar dados no banco:
        # estabelecimento
        to_sql(estabelecimento, name='estabelecimento', con=engine, if_exists='append', index=False)
        print('Arquivo ' + arquivos_estabelecimento[e] + ' / ' + str(part) + ' inserido com sucesso no banco de dados!')
        if linhas_lidas == NROWS and not ETL_TEST_MODE:
            part += 1
        else:
            break

try:
    del estabelecimento
except:
    pass
print('Arquivos de estabelecimento finalizados!')
estabelecimento_insert_end = time.time()
estabelecimento_Tempo_insert = round((estabelecimento_insert_end - estabelecimento_insert_start))
print('Tempo de execução do processo de estabelecimento (em segundos): ' + str(estabelecimento_Tempo_insert))

# #%%
# # Arquivos de empresa:
empresa_insert_start = time.time()
print("""
#######################
## Arquivos de EMPRESA:
#######################
""")

# Drop table antes do insert
cur.execute('DROP TABLE IF EXISTS "empresa";')
conn.commit()

for e in range(0, len(arquivos_empresa)):
    print('Trabalhando no arquivo: '+arquivos_empresa[e]+' [...]')
    try:
        del empresa
        gc.collect()
    except:
        pass

    #empresa = pd.DataFrame(columns=[0, 1, 2, 3, 4, 5, 6])
    empresa_dtypes = {0: object, 1: object, 2: 'Int32', 3: 'Int32', 4: object, 5: 'Int32', 6: object}
    extracted_file_path = os.path.join(extracted_files, arquivos_empresa[e])

    # Lido em pedaços (mesmo padrão do bloco de estabelecimento): alguns arquivos de empresa
    # trazem dezenas de milhões de linhas, e ler o arquivo inteiro de uma vez em um DataFrame só
    # já derrubou o processo por estouro de memória numa carga completa anterior.
    NROWS = ETL_MAX_ROWS or 2000000
    part = 0
    while True:
        empresa = pd.read_csv(filepath_or_buffer=extracted_file_path,
                              sep=';',
                              nrows=NROWS,
                              skiprows=NROWS * part,
                              header=None,
                              dtype=empresa_dtypes,
                              encoding='latin-1',
        )

        linhas_lidas = len(empresa)
        # Tratamento do arquivo antes de inserir na base:
        empresa = empresa.reset_index()
        del empresa['index']
        gc.collect()

        # Renomear colunas
        empresa.columns = ['cnpj_basico', 'razao_social', 'natureza_juridica', 'qualificacao_responsavel', 'capital_social', 'porte_empresa', 'ente_federativo_responsavel']

        # Replace "," por "."
        empresa['capital_social'] = empresa['capital_social'].apply(lambda x: x.replace(',','.'))
        empresa['capital_social'] = empresa['capital_social'].astype(float)

        if FILTRO_ATIVO:
            empresa = empresa[empresa['cnpj_basico'].astype(str).isin(cnpj_basico_filtrados)]
        # Gravar dados no banco:
        # Empresa
        to_sql(empresa, name='empresa', con=engine, if_exists='append', index=False)
        print('Arquivo ' + arquivos_empresa[e] + ' / ' + str(part) + ' inserido com sucesso no banco de dados!')
        if linhas_lidas == NROWS and not ETL_TEST_MODE:
            part += 1
        else:
            break

try:
    del empresa
except:
    pass
print('Arquivos de empresa finalizados!')
empresa_insert_end = time.time()
empresa_Tempo_insert = round((empresa_insert_end - empresa_insert_start))
print('Tempo de execução do processo de empresa (em segundos): ' + str(empresa_Tempo_insert))

#%%
# Arquivos de socios:
socios_insert_start = time.time()
print("""
######################
## Arquivos de SOCIOS:
######################
""")

# Drop table antes do insert
cur.execute('DROP TABLE IF EXISTS "socios";')
conn.commit()

if ETL_SKIP_SOCIOS:
    print('ETL_SKIP_SOCIOS ativo: tabela de sócios não será carregada.')
    arquivos_socios = []
for e in range(0, len(arquivos_socios)):
    print('Trabalhando no arquivo: '+arquivos_socios[e]+' [...]')
    try:
        del socios
        gc.collect()
    except:
        pass

    socios_dtypes = {0: object, 1: 'Int32', 2: object, 3: object, 4: 'Int32', 5: 'Int32', 6: 'Int32',
                     7: object, 8: object, 9: 'Int32', 10: 'Int32'}
    extracted_file_path = os.path.join(extracted_files, arquivos_socios[e])

    # Mesmo motivo do bloco de empresa: lido em pedaços para não estourar memória em arquivos
    # grandes.
    NROWS = ETL_MAX_ROWS or 2000000
    part = 0
    while True:
        socios = pd.read_csv(filepath_or_buffer=extracted_file_path,
                              sep=';',
                              nrows=NROWS,
                              skiprows=NROWS * part,
                              header=None,
                              dtype=socios_dtypes,
                              encoding='latin-1',
        )

        # Tratamento do arquivo antes de inserir na base:
        socios = socios.reset_index()
        del socios['index']
        gc.collect()

        # Renomear colunas
        socios.columns = ['cnpj_basico',
                          'identificador_socio',
                          'nome_socio_razao_social',
                          'cpf_cnpj_socio',
                          'qualificacao_socio',
                          'data_entrada_sociedade',
                          'pais',
                          'representante_legal',
                          'nome_do_representante',
                          'qualificacao_representante_legal',
                          'faixa_etaria']

        # Gravar dados no banco:
        # socios
        to_sql(socios, name='socios', con=engine, if_exists='append', index=False)
        print('Arquivo ' + arquivos_socios[e] + ' / ' + str(part) + ' inserido com sucesso no banco de dados!')
        if len(socios) == NROWS and not ETL_TEST_MODE:
            part += 1
        else:
            break

try:
    del socios
except:
    pass
print('Arquivos de socios finalizados!')
socios_insert_end = time.time()
socios_Tempo_insert = round((socios_insert_end - socios_insert_start))
print('Tempo de execução do processo de sócios (em segundos): ' + str(socios_Tempo_insert))

#%%
# Arquivos de simples:
simples_insert_start = time.time()
print("""
################################
## Arquivos do SIMPLES NACIONAL:
################################
""")

# Drop table antes do insert
cur.execute('DROP TABLE IF EXISTS "simples";')
conn.commit()

for e in range(0, len(arquivos_simples)):
    print('Trabalhando no arquivo: '+arquivos_simples[e]+' [...]')
    try:
        del simples
    except:
        pass

    # Verificar tamanho do arquivo:
    print('Lendo o arquivo ' + arquivos_simples[e]+' [...]')
    simples_dtypes = ({0: object, 1: object, 2: 'Int32', 3: 'Int32', 4: object, 5: 'Int32', 6: 'Int32'})
    extracted_file_path = os.path.join(extracted_files, arquivos_simples[e])

    if ETL_TEST_MODE:
        # Pula a contagem de linhas do arquivo inteiro (custa uma passada de I/O completa sobre
        # um arquivo que pode ter GBs) e lê só até ETL_MAX_ROWS em uma única parte.
        partes = 1
        nrows = ETL_MAX_ROWS
        skiprows = 0
        print('ETL_TEST_MODE ativo: lendo até ' + str(ETL_MAX_ROWS) + ' linha(s), sem contar o arquivo inteiro.')
    else:
        simples_lenght = sum(1 for line in open(extracted_file_path, "r"))
        print('Linhas no arquivo do Simples '+ arquivos_simples[e] +': '+str(simples_lenght))

        tamanho_das_partes = 1000000 # Registros por carga
        partes = round(simples_lenght / tamanho_das_partes)
        nrows = tamanho_das_partes
        skiprows = 0

    print('Este arquivo será dividido em ' + str(partes) + ' partes para inserção no banco de dados')

    for i in range(0, partes):
        print('Iniciando a parte ' + str(i+1) + ' [...]')
        simples = pd.DataFrame(columns=[1,2,3,4,5,6])

        simples = pd.read_csv(filepath_or_buffer=extracted_file_path,
                              sep=';',
                              nrows=nrows,
                              skiprows=skiprows,
                              header=None,
                              dtype=simples_dtypes,
                              encoding='latin-1',
        )

        # Tratamento do arquivo antes de inserir na base:
        simples = simples.reset_index()
        del simples['index']

        # Renomear colunas
        simples.columns = ['cnpj_basico',
                           'opcao_pelo_simples',
                           'data_opcao_simples',
                           'data_exclusao_simples',
                           'opcao_mei',
                           'data_opcao_mei',
                           'data_exclusao_mei']

        skiprows = skiprows+nrows

        if FILTRO_ATIVO:
            simples = simples[simples['cnpj_basico'].astype(str).isin(cnpj_basico_filtrados)]
        # Gravar dados no banco:
        # simples
        to_sql(simples, name='simples', con=engine, if_exists='append', index=False)
        print('Arquivo ' + arquivos_simples[e] + ' inserido com sucesso no banco de dados! - Parte '+ str(i+1))

        try:
            del simples
        except:
            pass

try:
    del simples
except:
    pass

print('Arquivos do simples finalizados!')
simples_insert_end = time.time()
simples_Tempo_insert = round((simples_insert_end - simples_insert_start))
print('Tempo de execução do processo do Simples Nacional (em segundos): ' + str(simples_Tempo_insert))

#%%
# Arquivos de cnae:
cnae_insert_start = time.time()
print("""
######################
## Arquivos de cnae:
######################
""")

# Drop table antes do insert
cur.execute('DROP TABLE IF EXISTS "cnae";')
conn.commit()

for e in range(0, len(arquivos_cnae)):
    print('Trabalhando no arquivo: '+arquivos_cnae[e]+' [...]')
    try:
        del cnae
    except:
        pass

    extracted_file_path = os.path.join(extracted_files, arquivos_cnae[e])
    cnae = pd.DataFrame(columns=[1,2])
    cnae = pd.read_csv(filepath_or_buffer=extracted_file_path, sep=';', skiprows=0, header=None, dtype='object', encoding='latin-1')

    # Tratamento do arquivo antes de inserir na base:
    cnae = cnae.reset_index()
    del cnae['index']

    # Renomear colunas
    cnae.columns = ['codigo', 'descricao']

    # Gravar dados no banco:
    # cnae
    to_sql(cnae, name='cnae', con=engine, if_exists='append', index=False)
    print('Arquivo ' + arquivos_cnae[e] + ' inserido com sucesso no banco de dados!')

try:
    del cnae
except:
    pass
print('Arquivos de cnae finalizados!')
cnae_insert_end = time.time()
cnae_Tempo_insert = round((cnae_insert_end - cnae_insert_start))
print('Tempo de execução do processo de cnae (em segundos): ' + str(cnae_Tempo_insert))

#%%
# Arquivos de moti:
moti_insert_start = time.time()
print("""
#########################################
## Arquivos de motivos da situação atual:
#########################################
""")

# Drop table antes do insert
cur.execute('DROP TABLE IF EXISTS "moti";')
conn.commit()

for e in range(0, len(arquivos_moti)):
    print('Trabalhando no arquivo: '+arquivos_moti[e]+' [...]')
    try:
        del moti
    except:
        pass

    moti_dtypes = ({0: 'Int32', 1: object})
    extracted_file_path = os.path.join(extracted_files, arquivos_moti[e])
    moti = pd.read_csv(filepath_or_buffer=extracted_file_path, sep=';', skiprows=0, header=None, dtype=moti_dtypes, encoding='latin-1')

    # Tratamento do arquivo antes de inserir na base:
    moti = moti.reset_index()
    del moti['index']

    # Renomear colunas
    moti.columns = ['codigo', 'descricao']

    # Gravar dados no banco:
    # moti
    to_sql(moti, name='moti', con=engine, if_exists='append', index=False)
    print('Arquivo ' + arquivos_moti[e] + ' inserido com sucesso no banco de dados!')

try:
    del moti
except:
    pass
print('Arquivos de moti finalizados!')
moti_insert_end = time.time()
moti_Tempo_insert = round((moti_insert_end - moti_insert_start))
print('Tempo de execução do processo de motivos da situação atual (em segundos): ' + str(moti_Tempo_insert))

#%%
# Arquivos de munic:
munic_insert_start = time.time()
print("""
##########################
## Arquivos de municípios:
##########################
""")

# Drop table antes do insert
cur.execute('DROP TABLE IF EXISTS "munic";')
conn.commit()

for e in range(0, len(arquivos_munic)):
    print('Trabalhando no arquivo: '+arquivos_munic[e]+' [...]')
    try:
        del munic
    except:
        pass

    munic_dtypes = ({0: 'Int32', 1: object})
    extracted_file_path = os.path.join(extracted_files, arquivos_munic[e])
    munic = pd.read_csv(filepath_or_buffer=extracted_file_path, sep=';', skiprows=0, header=None, dtype=munic_dtypes, encoding='latin-1')

    # Tratamento do arquivo antes de inserir na base:
    munic = munic.reset_index()
    del munic['index']

    # Renomear colunas
    munic.columns = ['codigo', 'descricao']

    # Gravar dados no banco:
    # munic
    to_sql(munic, name='munic', con=engine, if_exists='append', index=False)
    print('Arquivo ' + arquivos_munic[e] + ' inserido com sucesso no banco de dados!')

try:
    del munic
except:
    pass
print('Arquivos de munic finalizados!')
munic_insert_end = time.time()
munic_Tempo_insert = round((munic_insert_end - munic_insert_start))
print('Tempo de execução do processo de municípios (em segundos): ' + str(munic_Tempo_insert))

#%%
# Arquivos de natju:
natju_insert_start = time.time()
print("""
#################################
## Arquivos de natureza jurídica:
#################################
""")

# Drop table antes do insert
cur.execute('DROP TABLE IF EXISTS "natju";')
conn.commit()

for e in range(0, len(arquivos_natju)):
    print('Trabalhando no arquivo: '+arquivos_natju[e]+' [...]')
    try:
        del natju
    except:
        pass

    natju_dtypes = ({0: 'Int32', 1: object})
    extracted_file_path = os.path.join(extracted_files, arquivos_natju[e])
    natju = pd.read_csv(filepath_or_buffer=extracted_file_path, sep=';', skiprows=0, header=None, dtype=natju_dtypes, encoding='latin-1')

    # Tratamento do arquivo antes de inserir na base:
    natju = natju.reset_index()
    del natju['index']

    # Renomear colunas
    natju.columns = ['codigo', 'descricao']

    # Gravar dados no banco:
    # natju
    to_sql(natju, name='natju', con=engine, if_exists='append', index=False)
    print('Arquivo ' + arquivos_natju[e] + ' inserido com sucesso no banco de dados!')

try:
    del natju
except:
    pass
print('Arquivos de natju finalizados!')
natju_insert_end = time.time()
natju_Tempo_insert = round((natju_insert_end - natju_insert_start))
print('Tempo de execução do processo de natureza jurídica (em segundos): ' + str(natju_Tempo_insert))

#%%
# Arquivos de pais:
pais_insert_start = time.time()
print("""
######################
## Arquivos de país:
######################
""")

# Drop table antes do insert
cur.execute('DROP TABLE IF EXISTS "pais";')
conn.commit()

for e in range(0, len(arquivos_pais)):
    print('Trabalhando no arquivo: '+arquivos_pais[e]+' [...]')
    try:
        del pais
    except:
        pass

    pais_dtypes = ({0: 'Int32', 1: object})
    extracted_file_path = os.path.join(extracted_files, arquivos_pais[e])
    pais = pd.read_csv(filepath_or_buffer=extracted_file_path, sep=';', skiprows=0, header=None, dtype=pais_dtypes, encoding='latin-1')

    # Tratamento do arquivo antes de inserir na base:
    pais = pais.reset_index()
    del pais['index']

    # Renomear colunas
    pais.columns = ['codigo', 'descricao']

    # Gravar dados no banco:
    # pais
    to_sql(pais, name='pais', con=engine, if_exists='append', index=False)
    print('Arquivo ' + arquivos_pais[e] + ' inserido com sucesso no banco de dados!')

try:
    del pais
except:
    pass
print('Arquivos de pais finalizados!')
pais_insert_end = time.time()
pais_Tempo_insert = round((pais_insert_end - pais_insert_start))
print('Tempo de execução do processo de país (em segundos): ' + str(pais_Tempo_insert))

#%%
# Arquivos de qualificação de sócios:
quals_insert_start = time.time()
print("""
######################################
## Arquivos de qualificação de sócios:
######################################
""")

# Drop table antes do insert
cur.execute('DROP TABLE IF EXISTS "quals";')
conn.commit()

for e in range(0, len(arquivos_quals)):
    print('Trabalhando no arquivo: '+arquivos_quals[e]+' [...]')
    try:
        del quals
    except:
        pass

    quals_dtypes = ({0: 'Int32', 1: object})
    extracted_file_path = os.path.join(extracted_files, arquivos_quals[e])
    quals = pd.read_csv(filepath_or_buffer=extracted_file_path, sep=';', skiprows=0, header=None, dtype=quals_dtypes, encoding='latin-1')

    # Tratamento do arquivo antes de inserir na base:
    quals = quals.reset_index()
    del quals['index']

    # Renomear colunas
    quals.columns = ['codigo', 'descricao']

    # Gravar dados no banco:
    # quals
    to_sql(quals, name='quals', con=engine, if_exists='append', index=False)
    print('Arquivo ' + arquivos_quals[e] + ' inserido com sucesso no banco de dados!')

try:
    del quals
except:
    pass
print('Arquivos de quals finalizados!')
quals_insert_end = time.time()
quals_Tempo_insert = round((quals_insert_end - quals_insert_start))
print('Tempo de execução do processo de qualificação de sócios (em segundos): ' + str(quals_Tempo_insert))

#%%
insert_end = time.time()
Tempo_insert = round((insert_end - insert_start))

print("""
#############################################
## Processo de carga dos arquivos finalizado!
#############################################
""")

print('Tempo total de execução do processo de carga (em segundos): ' + str(Tempo_insert)) # Tempo de execução do processo (em segundos): 17.770 (4hrs e 57 min)

# ###############################
# Tamanho dos arquivos:
# empresa = 45.811.638
# estabelecimento = 48.421.619
# socios = 20.426.417
# simples = 27.893.923
# ###############################

#%%
# Criar índices na base de dados:
index_start = time.time()
print("""
#######################################
## Criar índices na base de dados [...]
#######################################
""")
cur.execute("""
create index if not exists empresa_cnpj on empresa(cnpj_basico);
commit;
create index if not exists estabelecimento_cnpj on estabelecimento(cnpj_basico);
commit;
create index if not exists socios_cnpj on socios(cnpj_basico);
commit;
create index if not exists simples_cnpj on simples(cnpj_basico);
commit;
create index if not exists estabelecimento_uf on estabelecimento(uf);
commit;
create index if not exists estabelecimento_municipio on estabelecimento(municipio);
commit;
create index if not exists estabelecimento_situacao_cadastral on estabelecimento(situacao_cadastral);
commit;
create index if not exists estabelecimento_cnae_fiscal_principal on estabelecimento(cnae_fiscal_principal);
commit;
""")
conn.commit()
print("""
############################################################
## Índices criados nas tabelas, para a coluna `cnpj_basico`:
   - empresa
   - estabelecimento
   - socios
   - simples

## Índices criados em `estabelecimento`, para os filtros da API
## de busca (`/empresas/search`):
   - uf
   - municipio
   - situacao_cadastral
   - cnae_fiscal_principal
############################################################
""")
index_end = time.time()
index_time = round(index_end - index_start)
print('Tempo para criar os índices (em segundos): ' + str(index_time))

#%%
print("""Processo 100% finalizado! Você já pode usar seus dados no BD!
 - Desenvolvido por: Aphonso Henrique do Amaral Rafael
 - Contribua com esse projeto aqui: https://github.com/aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ
""")