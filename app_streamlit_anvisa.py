
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Consulta Registro ANVISA", layout="wide")

st.title("Consulta automática de Registro ANVISA em planilhas")

st.write(
    "Envie sua planilha Excel contendo as colunas **MARCA** e **UN**. "
    "O sistema adicionará a coluna **Nº REGISTRO NA ANVISA** entre elas."
)

uploaded_file = st.file_uploader("Enviar planilha Excel", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    if "MARCA" not in df.columns or "UN" not in df.columns:
        st.error("A planilha precisa conter as colunas 'MARCA' e 'UN'.")
    else:
        cols = list(df.columns)

        marca_index = cols.index("MARCA")
        df.insert(marca_index + 1, "Nº REGISTRO NA ANVISA", "")

        st.success("Coluna criada com sucesso.")
        st.dataframe(df)

        output = "/tmp/planilha_resultado.xlsx"
        df.to_excel(output, index=False)

        with open(output, "rb") as f:
            st.download_button(
                "Baixar planilha atualizada",
                f,
                file_name="planilha_com_anvisa.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
