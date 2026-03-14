# ANVISA Registro por Lotes

## Onde colocar os bancos de dados no GitHub

Coloque os dois arquivos dentro da pasta `data/`:

- `data/TA_PRECO_MEDICAMENTO.csv`
- `data/TA_PRODUTO_SAUDE_SITE.csv`

## Estrutura do projeto

```text
app_streamlit_anvisa.py
requirements.txt
.streamlit/config.toml
data/TA_PRECO_MEDICAMENTO.csv
data/TA_PRODUTO_SAUDE_SITE.csv
```

## Arquivo principal no Streamlit Cloud

Use:

```text
app_streamlit_anvisa.py
```

## O que este sistema faz

1. Lê sua planilha Excel com várias abas.
2. Processa apenas os lotes selecionados, por padrão `L01` até `L08`.
3. Procura automaticamente o cabeçalho em cada aba.
4. Se a coluna **Nº REGISTRO NA ANVISA** não existir, ele cria essa coluna entre **MARCA** e **UN**.
5. Busca o registro mais compatível nas bases locais da ANVISA.
6. Preenche o número do registro encontrado.
7. Se a marca encontrada na base ativa for diferente da marca da planilha, ele pode substituir a marca.
8. Gera uma aba **AUDITORIA_ANVISA** com tudo o que foi encontrado, divergente ou não localizado.
9. Também consegue conferir uma planilha já preenchida.
10. Também consegue fazer conferência básica de PDF textual.

## Ajuste importante feito nesta versão

Foi removido o uso incompatível de `low_memory` com `engine='python'`.
Além disso, o leitor dos CSVs foi refeito para suportar:
- arquivos com cabeçalho real depois de várias linhas introdutórias;
- nomes de colunas diferentes;
- o arquivo de produto para saúde que você enviou.
