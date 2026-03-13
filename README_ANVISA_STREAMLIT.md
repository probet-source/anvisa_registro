# Validador ANVISA para Planilhas

Aplicação em Streamlit para:
- ler a planilha de proposta;
- conferir se a marca sugerida está compatível com registros ativos/válidos da ANVISA;
- substituir a marca por uma marca/detentor ativo quando necessário;
- preencher a coluna **Nº REGISTRO NA ANVISA**;
- gerar uma aba **AUDITORIA_ANVISA** com o histórico das alterações.

## Como rodar localmente

```bash
pip install -r requirements_anvisa_streamlit.txt
streamlit run app_streamlit_anvisa.py
```

## Como publicar no Streamlit Cloud

1. Crie um repositório no GitHub.
2. Envie estes arquivos:
   - `app_streamlit_anvisa.py`
   - `requirements_anvisa_streamlit.txt`
   - `README_ANVISA_STREAMLIT.md`
3. No Streamlit Cloud, escolha o repositório e selecione `app_streamlit_anvisa.py` como arquivo principal.

## O que a aplicação faz

- Usa as bases públicas da ANVISA para medicamentos e produtos para saúde.
- Filtra registros ativos/válidos/regularizados quando essa informação está disponível no arquivo.
- Compara descrição + marca da planilha com os cadastros da ANVISA.
- Quando a marca da planilha não encontra correspondência segura ativa, substitui pela marca/detentor compatível mais forte.
- Destaca em amarelo as células alteradas/preenchidas.

## Saídas

- Planilha Excel com a coluna `Nº REGISTRO NA ANVISA` preenchida.
- Aba `AUDITORIA_ANVISA`.
- CSV `auditoria_anvisa.csv`.

## Observação importante

O matching é heurístico. Em itens muito genéricos, a auditoria final humana ainda é recomendada.
