FROM python:3.11-slim

WORKDIR /app

# requirements.txt vive na raiz do repo (não em code/), por isso o build context deste serviço
# (ver docker-compose.yml) é a raiz do repo, com este Dockerfile referenciado via "dockerfile:".
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY code/ETL_coletar_dados_e_gravar_BD.py .

CMD ["python", "ETL_coletar_dados_e_gravar_BD.py"]
