import pandas as pd
import geopandas as gpd
import numpy as np
from impala.dbapi import connect
import pyproj
import requests
import tempfile
import os
import itertools
 
# Caminho do arquivo de credenciais da BISP
caminho_cred = 'C:\\Users\\x20081782\\OneDrive - CAMG\\Área de Trabalho\\Paineis\\Credenciamento Python.txt'
# URL do arquivo no GitHub
url = 'https://github.com/barbaraoliveira-hub/SAD_IBGE96/raw/main/SAD96_003.GSB'
# Caminho do arquivo BDHC Reds Desconsiderados
caminho_bdhc = 'C:\\Users\\x20081782\\OneDrive - CAMG\\Área de Trabalho\\BDHC\\Abril, Maio e Junho 2025\\TRATADO - Homicídios Consumados - Vítima - Fatal - MG - 2012 a 2025 (atualização ABR-MAI-JUN).xlsx'
# Caminho do arquivo de Grupo Local Imediato
caminho_local = 'C:\\Users\\x20081782\\Downloads\\Grupo_Local_Imediato (1).xlsx'
# Caminho do arquivo de Grupo Local Instrumento
caminho_meio = 'C:\\Users\\x20081782\\Downloads\\instrumento.xlsx'
# Caminho da pasta onde os arquivos serão salvos
caminho_pasta = 'C:\\Users\\x20081782\\Downloads\\BDjunho'
 
## PARTE 1 - EXTRAÇÃO DA BASE DE DADOS DA BISP
 
# Função para ler o arquivo de credenciais
def get_credentials(file_path):
    credentials = {}
    with open(file_path, 'r') as file:
        for line in file:
            key, value = line.strip().split('=')
            credentials[key] = value
    return credentials
 
# Função para conectar ao banco de dados
def get_conn_and_cursor(db='db_bisp_reds_reporting', credentials_file = caminho_cred):
    credentials = get_credentials(credentials_file)
    conn = connect(host='10.100.62.20', port=21051, use_ssl=True, auth_mechanism="PLAIN",
                   user=credentials['username'], password=credentials['password'], database=db)
    cursor = conn.cursor()
    return conn, cursor
 
# Função para executar query e retornar dataframe
def executa_query_retorna_df(query, db='db_bisp_reds_reporting'):
    conn, cursor = get_conn_and_cursor(db)  
    cursor.execute(query)
    results = cursor.fetchall()
    columns = [c[0] for c in cursor.description]
    df = pd.DataFrame(results, columns=columns)
    conn.close()
    return df
 
# Função para listar tabelas no banco de dados
def tabelas(filtro='', db='db_bisp_reds_reporting'):
    conn, cursor = get_conn_and_cursor(db)
    cursor.execute('SHOW TABLES')
    tabelas_nomes = cursor.fetchall()    
    conn.close()
    tabelas_filtradas = [tupla_tabela[0] for tupla_tabela in tabelas_nomes if filtro in tupla_tabela[0]]
    return tabelas_filtradas
 
# Função para listar bancos de dados
def bancos_de_dados():
    conn, cursor = get_conn_and_cursor()
    try:
        cursor.execute("SHOW DATABASES")
        databases = cursor.fetchall()
        accessible_databases = []
        for db in databases:
            try:
                cursor.execute(f"USE {db[0]}")
                accessible_databases.append(db[0])
            except:
                pass
        return accessible_databases
    finally:
        cursor.close()
        conn.close()
 
# Consulta ao banco (script do dbeaver: no exemplo abaixo há um join entre a tabela de ocorrências e envolvidos)
try:
    query = '''SELECT oco.numero_ocorrencia,
                      oco.qtd_ocorrencia,
                      oco.natureza_descricao,
                      oco.natureza_consumado,
                      CAST (oco.data_hora_fato as date) as data_fato,
                      YEAR (oco.data_hora_fato) as ano_fato,
                      MONTH (oco.data_hora_fato) as mes_numerico_fato,
                      SUBSTRING(CAST(oco.data_hora_fato AS STRING), 12, 8) AS horario_fato,
                      oco.motivo_presumido_descricao_longa,
                      oco.instrumento_utilizado_codigo,
                      oco.local_imediato_longa,
                      oco.tipo_logradouro_descricao,
                      oco.descricao_endereco,
                      oco.nome_bairro,
                      oco.nome_municipio,
                      oco.codigo_municipio,
                      oco.ocorrencia_uf,
                      oco.unidade_responsavel_registro_nome,
                      oco.numero_latitude,
                      oco.numero_longitude,
                      mun.risp_completa,
                      mun.rmbh
               FROM db_bisp_reds_reporting.tb_ocorrencia AS oco
               LEFT JOIN db_bisp_shared.tb_populacao_risp as mun
                    ON oco.codigo_municipio = mun.codigo_ibge
               WHERE oco.data_hora_fato >= '2012-01-01 00:00:00.000'
               AND oco.data_hora_fato < ADD_MONTHS(DATE_TRUNC('MONTH', NOW()), 0)
               AND oco.ocorrencia_uf = 'MG'
               AND oco.ind_estado IN ('F', 'R')
               AND ((oco.natureza_codigo in ('B01121','D01213', 'C01157', 'C01158', 'D01217', 'B01148', 'C01159') AND  oco.natureza_consumado IN ('CONSUMADO'))
               OR (oco.natureza_codigo in ('B01121', 'D01213', 'C01157', 'C01158', 'D01217', 'B01148') AND  oco.natureza_consumado IN ('TENTADO')))
               '''
   
    df = executa_query_retorna_df(query, db='db_bisp_reds_reporting')
   
   
 
except Exception as e:
    print(f"Erro ao consultar a tabela 'tb_ocorrencia': {e}")
 
# Extração da tabela com municipio, risp e rmbh
try:
    query2 = '''SELECT
                      mun.risp,
                      mun.rmbh,
                      mun.codigo_ibge as codigo_municipio,
                      mun.descricao_municipio
               FROM db_bisp_shared.tb_populacao_risp as mun
               '''
   
    mun = executa_query_retorna_df(query2, db='db_bisp_shared')
   
   
 
except Exception as e:
    print(f"Erro ao consultar a tabela 'tb_municipio': {e}")
 
## PARTE 2 - TRATAMENTO DOS DADOS
 
# Tansformando Lat Long para SIRGAS 2000
# Baixar o arquivo temporariamente
response = requests.get(url)
response.raise_for_status()  # Garantir que o download foi bem-sucedido
 
# Criar um arquivo temporário para o arquivo baixado
with tempfile.NamedTemporaryFile(delete=False, suffix='.GSB') as temp_file:
    temp_file.write(response.content)
    temp_file_path = temp_file.name
 
# Define o pipeline de transformação
transformer = pyproj.Transformer.from_pipeline(
    f"+proj=pipeline +step +proj=axisswap +order=2,1 "
    "+step +proj=unitconvert +xy_in=deg +xy_out=rad "
    f"+step +proj=hgridshift +grids={temp_file_path} "
    "+step +proj=unitconvert +xy_in=rad +xy_out=deg "
    "+step +proj=axisswap +order=2,1"
)
 
# Função para transformar coordenadas
def transformar_coordenadas(lat, lon):
    if pd.isna(lat) or pd.isna(lon):
        return pd.Series(["", ""], index=['Latitude SIRGAS', 'Longitude SIRGAS'])
    lat_sirgas, lon_sirgas = transformer.transform(lat, lon)
    return pd.Series([lat_sirgas, lon_sirgas], index=['Latitude SIRGAS', 'Longitude SIRGAS'])
 
# Criar novas colunas com as coordenadas transformadas no DataFrame retornado pela consulta SQL
df[['Latitude SIRGAS', 'Longitude SIRGAS']] = df.apply(
    lambda row: transformar_coordenadas(row['numero_latitude'], row['numero_longitude']),
    axis=1
)
 
# Convertendo a coluna 'Valor' para string e substituindo ponto por vírgula
df['Latitude SIRGAS'] = df['Latitude SIRGAS'].astype(str).str.replace("inf", '', regex=False)
df['Longitude SIRGAS'] = df['Longitude SIRGAS'].astype(str).str.replace("inf", '', regex=False)
df['Latitude SIRGAS'] = pd.to_numeric(df['Latitude SIRGAS'])
df['Longitude SIRGAS'] = pd.to_numeric(df['Longitude SIRGAS'])
 
# fim da dtransformação lat long
 
# Substitui bairros em branco por INVALIDO e cria a coluna Bairro_Municipio
df['nome_bairro'] = df['nome_bairro'].replace('', 'INVALIDO').fillna('INVALIDO')
df['bairro-município'] = df['nome_bairro'] + ', ' + df['nome_municipio']
 
#cria a coluna natureza completa
df['Natureza Principal Completa'] = df['natureza_descricao'] + ' ' + df['natureza_consumado']
 
# Converter a coluna 'Hora' para tipo datetime, considerando apenas o tempo
df['horario_fato'] = pd.to_datetime(df['horario_fato'], format='%H:%M:%S').dt.time
 
# Função para determinar a faixa de 6 horas
def get_6h_cluster(time):
    if pd.to_datetime(time, format='%H:%M:%S').hour < 6:
        return '00:00 a 05:59'
    elif pd.to_datetime(time, format='%H:%M:%S').hour < 12:
        return '06:00 a 11:59'
    elif pd.to_datetime(time, format='%H:%M:%S').hour < 18:
        return '12:00 a 17:59'
    else:
        return '18:00 a 23:59'
 
# Aplicar a função para criar a nova coluna faixa de 1 hora
df['Faixa 6 Horas Fato'] = df['horario_fato'].apply(get_6h_cluster)
 
# Função para determinar a faixa de 1 hora
def get_1h_cluster(time):
    hour = pd.to_datetime(time, format='%H:%M:%S').hour
    start_hour = hour
    end_hour = (hour + 1) % 24
    start_time = f'{start_hour:02}:00'
    end_time = f'{end_hour:02}:59'
    return f'{start_time} a {end_time}'
 
# Aplicar a função para criar a nova coluna 'Faixa de Hora'
df['Faixa 1 Hora Fato'] = df['horario_fato'].apply(get_1h_cluster)
 
#cria a coluna dia da semana
df['data_fato'] = pd.to_datetime(df['data_fato'])
dias_da_semana = {
    'Monday': 'Segunda-feira',
    'Tuesday': 'Terça-feira',
    'Wednesday': 'Quarta-feira',
    'Thursday': 'Quinta-feira',
    'Friday': 'Sexta-feira',
    'Saturday': 'Sábado',
    'Sunday': 'Domingo'
}
df['Dia da Semana'] = df['data_fato'].dt.day_name().map(dias_da_semana)
 
# cria uma coluna para Homicidio Consumado puxando do BDHC se o Reds é desconsiderado ou não (naturezas diferentes de HC são consideradas)
 
hc = pd.read_excel(caminho_bdhc)
 
def criar_colunahc(df, hc):
    # Função que retorna o valor desejado
    def obter_valorhc(row):
        if row['Natureza Principal Completa'] == 'HOMICIDIO CONSUMADO':
            # Tenta encontrar a correspondência em hc
            correspondente = hc.loc[hc['Número REDS'] == row['numero_ocorrencia'], 'Nº REDS considerado']
            if not correspondente.empty:
                return correspondente.values[0]  # Retorna o valor correspondente
            else:
                return 'NÃO AUDITADO'  # Se não encontrar correspondência
        else:
            return 'NÃO'  # Para outros casos
   
    # Aplica a função linha por linha
    df['REDS desconsiderado'] = df.apply(obter_valorhc, axis=1)
    return df
 
# Chamando a função
df = criar_colunahc(df, hc)
 
# Exclui as linhas de HC desconsiderados ou não auditados
df = df[~df['REDS desconsiderado'].isin(['SIM', 'NÃO AUDITADO'])]
 
# cria a coluna grupo local imediato
lc = pd.read_excel(caminho_local)
 
def criar_coluna_gl(df, lc):
    # Função que retorna o valor desejado
    def obter_valorgl(row):
        if row['local_imediato_longa'] != '':
            # Tenta encontrar a correspondência em hc
            correspondente = lc.loc[lc['Descricao Longa Local Imediato'] == row['local_imediato_longa'], 'Descricao Longa Grupo Local Imediato']
            if not correspondente.empty:
                return correspondente.values[0]  # Retorna o valor correspondente
            else:
                return 'NÃO INFORMADO'  # Se não encontrar correspondência
        else:
            return 'NÃO INOFRMADO'  # Para outros casos
   
    # Aplica a função linha por linha
    df['Grupo Local Imediato'] = df.apply(obter_valorgl, axis=1)
    return df
 
# Chamando a função
df = criar_coluna_gl(df, lc)
 
# cria a coluna grupo instrumento utilizad
inst = pd.read_excel(caminho_meio)
 
df['instrumento_utilizado_codigo'] = pd.to_numeric(df['instrumento_utilizado_codigo'])
inst['instrumento_utilizado_codigo'] = pd.to_numeric(inst['instrumento_utilizado_codigo'])
 
def criar_coluna_inst(df, inst):
    # Função que retorna o valor desejado
    def obter_valorinst(row):
            # Tenta encontrar a correspondência em instrumentos
            correspondente = inst.loc[inst['instrumento_utilizado_codigo'] == row['instrumento_utilizado_codigo'], 'instrumento_utilizado_grupo']
            if not correspondente.empty:
                return correspondente.values[0]  # Retorna o valor correspondente
            else:
                return 'MEIOS NÃO IDENTIFICADOS'  # Se não encontrar correspondência
   
    # Aplica a função linha por linha
    df['instrumento_utilizado_descricao_longa'] = df.apply(obter_valorinst, axis=1)
    return df
 
# Chamando a função
df = criar_coluna_inst(df, inst)
 
# Exibe as primeiras linhas do DataFrame
print(df.head())
 
 
## PARTE 3 - SALVAR AS BASES DE DADOS NO SHAREPOINT
 
# muda a ordem das colunas
nova_ordem = ['numero_ocorrencia', 'qtd_ocorrencia', 'natureza_descricao', 'natureza_consumado', 'Natureza Principal Completa', 'ano_fato', 'mes_numerico_fato', 'data_fato', 'Dia da Semana', 'horario_fato', 'Faixa 1 Hora Fato', 'Faixa 6 Horas Fato', 'motivo_presumido_descricao_longa', 'instrumento_utilizado_descricao_longa', 'Grupo Local Imediato', 'local_imediato_longa', 'tipo_logradouro_descricao', 'descricao_endereco', 'nome_bairro', 'bairro-município', 'nome_municipio', 'codigo_municipio', 'ocorrencia_uf', 'unidade_responsavel_registro_nome', 'risp_completa', 'rmbh', 'numero_latitude', 'numero_longitude', 'Latitude SIRGAS', 'Longitude SIRGAS', 'REDS desconsiderado']
df = df[nova_ordem]
 
# Salva a base de dados completa em csv
 
df.to_csv(f'{caminho_pasta}BD_CV.csv', sep=';', decimal=',', index=False, encoding='utf-8-sig')
 
 
# Para salvar alvos de CV em todo o período desde 2012 em excel - separando para dar menos de 1mi de linhas
# Filtrando o DataFrame por ano
df_2012_2021 = df[(df['ano_fato'] >= 2012) & (df['ano_fato'] <= 2021)]
df_2022_presente = df[df['ano_fato'] >= 2022]
 
# Salvando os DataFrames em arquivos distintos
df_2012_2021.to_excel(f'{caminho_pasta}Crimes_Violentos_2012 a 2021.xlsx', index=False)
df_2022_presente.to_excel(f'{caminho_pasta}Crimes_Violentos_2022 a presente.xlsx', index=False)
 
 
# Criando a planilha de registros por municipios
# Agrupando por mês, ano, natureza e município e contando as ocorrências
tabela_contagem = df.groupby(['mes_numerico_fato', 'ano_fato', 'Natureza Principal Completa', 'codigo_municipio']).size().reset_index(name='Registros')
 
# Criando um DataFrame com todas as combinações possíveis
all_combinations = pd.DataFrame(list(itertools.product(
    tabela_contagem['mes_numerico_fato'].unique(),
    tabela_contagem['ano_fato'].unique(),
    tabela_contagem['Natureza Principal Completa'].unique(),
    mun['codigo_municipio']
)), columns=['mes_numerico_fato', 'ano_fato', 'Natureza Principal Completa', 'codigo_municipio'])
 
# Realizando um left join e preenchendo os valores NaN com 0
tabela_completa = pd.merge(all_combinations, tabela_contagem, on=['mes_numerico_fato', 'ano_fato', 'Natureza Principal Completa', 'codigo_municipio'], how='left')
tabela_completa['Registros'] = tabela_completa['Registros'].fillna(0)
tabela_completa = pd.merge(tabela_completa, mun, on=['codigo_municipio'], how='left')
 
# Salva a planilha em excel dividindo em 2 abas
nova_ordem2 = ['Registros', 'Natureza Principal Completa', 'descricao_municipio', 'codigo_municipio', 'mes_numerico_fato', 'ano_fato', 'risp', 'rmbh']
tabela_completa = tabela_completa[nova_ordem2]
tabela_completa = tabela_completa.sort_values(by=['ano_fato', 'mes_numerico_fato'])
 
tabela_2012_2018 = tabela_completa[(tabela_completa['ano_fato'] >= 2012) & (tabela_completa['ano_fato'] <= 2018)]
tabela_2019_presente = tabela_completa[tabela_completa['ano_fato'] >= 2019]
 
with pd.ExcelWriter(f'{caminho_pasta}CV_Contagem mun.xlsx') as writer:
    tabela_2012_2018.to_excel(writer, sheet_name='2012-2018', index=False)
    tabela_2019_presente.to_excel(writer, sheet_name='2019-2024', index=False)
