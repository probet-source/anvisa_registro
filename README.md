# ANVISA Registro por Lotes - versão revisada

## O que foi corrigido nesta versão

A versão anterior tinha dois pontos frágeis:

1. leitura dos CSVs com formatos diferentes;
2. processamento pesado sem feedback visual, dando a impressão de que o botão não fazia nada.

Nesta versão:

- o leitor dos CSVs foi refeito;
- a busca foi otimizada com índice por tokens;
- foi adicionada barra de progresso;
- os bancos já ficam dentro da pasta `data/`.

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

1. Lê a planilha Excel com várias abas.
2. Processa apenas os lotes escolhidos, por padrão `L01` até `L08`.
3. Localiza automaticamente o cabeçalho.
4. Se a coluna **Nº REGISTRO NA ANVISA** não existir, cria entre **MARCA** e **UN**.
5. Busca o registro mais compatível nas bases locais.
6. Preenche o número do registro.
7. Pode ajustar a marca se encontrar uma marca ativa diferente.
8. Cria a aba **AUDITORIA_ANVISA**.
9. Consegue conferir planilha já preenchida.
10. Consegue fazer conferência básica de PDF textual.

## Observação honesta

Mesmo nesta versão, a qualidade do resultado depende da descrição do item na planilha e da existência de correspondência na base.
Ou seja: o sistema fica funcional e operante, mas alguns itens ainda podem sair como `NAO ENCONTRADO` quando a descrição não casar bem com a base oficial.
