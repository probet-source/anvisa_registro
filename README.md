# ANVISA Registro por Lotes

Projeto em Streamlit para:

- processar planilhas Excel com múltiplas abas
- atuar apenas nos lotes L01 a L08
- inserir a coluna **Nº REGISTRO NA ANVISA** quando ela não existir
- preencher registros com base nos CSVs da ANVISA
- ajustar a marca quando encontrar uma marca ativa compatível
- conferir planilhas já preenchidas
- fazer conferência básica de PDFs textuais

## Estrutura

```text
app_streamlit_anvisa.py
requirements.txt
.streamlit/config.toml
data/TA_PRECO_MEDICAMENTO.csv
data/TA_CONSULTA_PRODUTOS_SAUDE.CSV
```

## Como subir no GitHub

1. Envie todos os arquivos para a raiz do repositório.
2. Se quiser evitar upload manual no app, coloque os CSVs oficiais dentro da pasta `data/`.
3. No Streamlit Cloud, defina o arquivo principal como:

```text
app_streamlit_anvisa.py
```

## Observação importante

Os registros só serão pesquisados se a base da ANVISA estiver disponível:
- por upload na sidebar do app, ou
- pelos arquivos na pasta `data/`.

Sem esses CSVs, o app abre normalmente, mas não consegue preencher os registros.
