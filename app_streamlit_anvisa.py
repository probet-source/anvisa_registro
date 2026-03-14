import io
import re
import unicodedata
from pathlib import Path

import pandas as pd
import pdfplumber
import streamlit as st
from openpyxl import load_workbook
from openpyxl.styles import PatternFill
from rapidfuzz import fuzz

# =========================================================
# CONFIGURAÇÃO
# =========================================================
st.set_page_config(page_title="ANVISA - Registro por Lotes", layout="wide")

DATA_DIR = Path("data")
MED_CSV_DEFAULT = DATA_DIR / "TA_PRECO_MEDICAMENTO.csv"
PROD_CSV_DEFAULT = DATA_DIR / "TA_CONSULTA_PRODUTOS_SAUDE.CSV"

LOTES_PADRAO = [f"L0{i}" for i in range(1, 9)]

FILL_HEADER = PatternFill(fill_type="solid", start_color="C8E6C9", end_color="C8E6C9")
FILL_ALTERADO = PatternFill(fill_type="solid", start_color="FFF59D", end_color="FFF59D")
FILL_OK = PatternFill(fill_type="solid", start_color="C8E6C9", end_color="C8E6C9")
FILL_ERRO = PatternFill(fill_type="solid", start_color="FFCDD2", end_color="FFCDD2")


# =========================================================
# FUNÇÕES BÁSICAS
# =========================================================
def normalizar_texto(txt):
    if txt is None:
        return ""
    txt = str(txt).strip().upper()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = txt.replace("\n", " ").replace("\r", " ")
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def apenas_digitos(txt):
    if txt is None:
        return ""
    return re.sub(r"\D", "", str(txt))


def limpar_desc(desc):
    desc = normalizar_texto(desc)

    trocas = {
        "SOL. ORAL.": "SOLUCAO ORAL",
        "SOL ORAL": "SOLUCAO ORAL",
        "SUSP. ORAL.": "SUSPENSAO ORAL",
        "SUSP ORAL": "SUSPENSAO ORAL",
        "COMPRIMIDO": "CPR",
        "COMPRIMIDOS": "CPR",
        "CAPSULA": "CAP",
        "CAPSULAS": "CAP",
        "AMPOLA": "AMP",
        "AMPOLAS": "AMP",
        "FRASCO": "FR",
        "FRASCOS": "FR",
        "BISNAGA": "BISN",
        "BISN.": "BISN",
        "MILILITROS": "ML",
        "MILILITRO": "ML",
        "GRAMAS": "G",
        "GRAMA": "G",
        "MICROGRAMAS": "MCG",
        "MICROGRAMA": "MCG",
        "UNIDADES INTERNACIONAIS": "UI",
        "INJETÁVEL": "INJETAVEL",
        "SUSPENSÃO": "SUSPENSAO",
        "SOLUÇÃO": "SOLUCAO",
    }

    for de, para in trocas.items():
        desc = desc.replace(de, para)

    desc = re.sub(r"[.,;:()+\-/%]", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip()
    return desc


def eh_linha_vazia_ou_total(valor_desc):
    v = normalizar_texto(valor_desc)
    if not v:
        return True

    termos_ruins = {
        "TOTAL",
        "TOTAL DO LOTE",
        "SUBTOTAL",
        "VALOR TOTAL",
        "TOTAL GERAL",
    }
    return v in termos_ruins


def parece_registravel(desc):
    d = limpar_desc(desc)

    palavras_chave = [
        "MG", "ML", "MCG", "G", "UI",
        "SOLUCAO", "SUSPENSAO", "INJETAVEL",
        "CPR", "CAP", "AMP", "FR", "BOLSA", "BISN",
        "CREME", "POMADA", "XAROPE", "GEL", "SOLUCAO ORAL",
        "SERINGA", "CATETER", "EQUIPO", "LUVA", "CURATIVO",
        "KIT", "TESTE", "REAGENTE"
    ]

    return any(p in d for p in palavras_chave)


def primeira_coluna_existente(df, candidatos):
    norm = {normalizar_texto(c): c for c in df.columns}

    for cand in candidatos:
        cand_norm = normalizar_texto(cand)
        for real_norm, real_col in norm.items():
            if cand_norm == real_norm:
                return real_col

    for cand in candidatos:
        cand_norm = normalizar_texto(cand)
        for real_norm, real_col in norm.items():
            if cand_norm in real_norm:
                return real_col

    return None


# =========================================================
# CABEÇALHO E COLUNAS DA PLANILHA
# =========================================================
def achar_linha_cabecalho(ws):
    melhores = []

    for r in range(1, min(ws.max_row, 20) + 1):
        valores = [normalizar_texto(ws.cell(r, c).value) for c in range(1, min(ws.max_column, 15) + 1)]
        score = 0

        for v in valores:
            if v == "ITEM":
                score += 2
            if "DESCRICAO" in v:
                score += 3
            if v == "MARCA":
                score += 2
            if v in ("UN", "UND", "UNIDADE"):
                score += 2
            if "QUANT" in v:
                score += 1
            if "V. UNIT" in v or "V UNIT" in v:
                score += 1
            if "ANVISA" in v:
                score += 2

        melhores.append((score, r))

    melhores.sort(reverse=True)
    if not melhores:
        return None

    return melhores[0][1] if melhores[0][0] >= 5 else None


def mapear_colunas(ws, header_row):
    mapa = {}

    for c in range(1, ws.max_column + 1):
        nome = normalizar_texto(ws.cell(header_row, c).value)

        nome = nome.replace("Nº", "N ").replace("NO ", "N ").replace("N.", "N ")

        if nome == "ITEM":
            mapa["ITEM"] = c
        elif "DESCRICAO" in nome:
            mapa["DESCRICAO"] = c
        elif nome == "MARCA":
            mapa["MARCA"] = c
        elif "REGISTRO" in nome and "ANVISA" in nome:
            mapa["ANVISA"] = c
        elif nome in ("UN", "UND", "UNIDADE"):
            mapa["UN"] = c
        elif "QUANT" in nome:
            mapa["QUANT"] = c
        elif "V. UNIT" in nome or "V UNIT" in nome:
            mapa["V_UNIT"] = c
        elif "V. TOTAL" in nome or "V TOTAL" in nome:
            mapa["V_TOTAL"] = c

    return mapa


def inserir_coluna_anvisa(ws, header_row):
    """
    Se a coluna já existir, retorna a coluna existente.
    Se não existir, insere entre MARCA e UN.
    """
    mapa = mapear_colunas(ws, header_row)

    if "ANVISA" in mapa:
        return mapa["ANVISA"], False

    if "MARCA" not in mapa:
        return None, False

    col_marca = mapa["MARCA"]
    ws.insert_cols(col_marca + 1)
    ws.cell(header_row, col_marca + 1).value = "Nº REGISTRO NA ANVISA"
    ws.cell(header_row, col_marca + 1).fill = FILL_HEADER
    return col_marca + 1, True


# =========================================================
# LEITURA DAS BASES ANVISA
# =========================================================
def ler_csv_flex(origem):
    return pd.read_csv(
        origem,
        sep=None,
        engine="python",
        dtype=str,
        encoding_errors="ignore",
        low_memory=False
    ).fillna("")


def carregar_bases(arquivo_med_upload=None, arquivo_prod_upload=None):
    """
    Prioridade:
    1) upload manual na sidebar
    2) arquivos locais na pasta data/
    """
    med_src = None
    prod_src = None

    if arquivo_med_upload is not None:
        med_src = arquivo_med_upload

    elif MED_CSV_DEFAULT.exists():
        med_src = MED_CSV_DEFAULT

    if arquivo_prod_upload is not None:
        prod_src = arquivo_prod_upload

    elif PROD_CSV_DEFAULT.exists():
        prod_src = PROD_CSV_DEFAULT

    if med_src is None:
        raise FileNotFoundError(
            "Base de medicamentos não encontrada. "
            "Envie o CSV da ANVISA na sidebar ou coloque em data/TA_PRECO_MEDICAMENTO.csv"
        )

    if prod_src is None:
        raise FileNotFoundError(
            "Base de produtos para saúde não encontrada. "
            "Envie o CSV da ANVISA na sidebar ou coloque em data/TA_CONSULTA_PRODUTOS_SAUDE.CSV"
        )

    med = ler_csv_flex(med_src)
    prod = ler_csv_flex(prod_src)

    # -------------------------
    # MEDICAMENTOS
    # -------------------------
    col_prod_med = primeira_coluna_existente(med, [
        "PRODUTO", "NOME PRODUTO", "NOME_DO_PRODUTO", "NOME COMERCIAL"
    ])
    col_apres_med = primeira_coluna_existente(med, [
        "APRESENTACAO", "DESCRICAO APRESENTACAO", "APRESENTACAO COMERCIAL"
    ])
    col_reg_med = primeira_coluna_existente(med, [
        "REGISTRO", "NUMERO REGISTRO", "NUMERO DO REGISTRO"
    ])
    col_lab_med = primeira_coluna_existente(med, [
        "LABORATORIO", "DETENTOR", "EMPRESA", "RAZAO SOCIAL"
    ])
    col_sit_med = primeira_coluna_existente(med, [
        "SITUACAO", "STATUS", "SITUACAO REGISTRO"
    ])

    med_norm = pd.DataFrame({
        "produto": med[col_prod_med] if col_prod_med else "",
        "apresentacao": med[col_apres_med] if col_apres_med else "",
        "registro": med[col_reg_med] if col_reg_med else "",
        "marca": med[col_lab_med] if col_lab_med else "",
        "situacao": med[col_sit_med] if col_sit_med else "",
    })

    med_norm["produto_apresentacao"] = (
        med_norm["produto"].astype(str) + " " + med_norm["apresentacao"].astype(str)
    ).map(limpar_desc)
    med_norm["marca_norm"] = med_norm["marca"].map(normalizar_texto)
    med_norm["registro_dig"] = med_norm["registro"].map(apenas_digitos)
    med_norm["situacao_norm"] = med_norm["situacao"].map(normalizar_texto)

    med_norm = med_norm[
        med_norm["produto_apresentacao"].astype(str).str.len() > 2
    ].copy()

    # -------------------------
    # PRODUTOS PARA SAÚDE
    # -------------------------
    col_prod_ps = primeira_coluna_existente(prod, [
        "NOME TECNICO DO PRODUTO",
        "NOME COMERCIAL DO PRODUTO",
        "NOME PRODUTO",
        "PRODUTO"
    ])
    col_reg_ps = primeira_coluna_existente(prod, [
        "NUMERO REGISTRO", "REGISTRO", "NUMERO DO REGISTRO", "NUMERO CADASTRO"
    ])
    col_det_ps = primeira_coluna_existente(prod, [
        "DETENTOR DO REGISTRO", "DETENTOR", "EMPRESA", "RAZAO SOCIAL"
    ])
    col_sit_ps = primeira_coluna_existente(prod, [
        "SITUACAO", "STATUS", "SITUACAO REGISTRO"
    ])

    prod_norm = pd.DataFrame({
        "produto": prod[col_prod_ps] if col_prod_ps else "",
        "registro": prod[col_reg_ps] if col_reg_ps else "",
        "marca": prod[col_det_ps] if col_det_ps else "",
        "situacao": prod[col_sit_ps] if col_sit_ps else "",
    })

    prod_norm["produto_apresentacao"] = prod_norm["produto"].map(limpar_desc)
    prod_norm["marca_norm"] = prod_norm["marca"].map(normalizar_texto)
    prod_norm["registro_dig"] = prod_norm["registro"].map(apenas_digitos)
    prod_norm["situacao_norm"] = prod_norm["situacao"].map(normalizar_texto)

    prod_norm = prod_norm[
        prod_norm["produto_apresentacao"].astype(str).str.len() > 2
    ].copy()

    return med_norm, prod_norm


# =========================================================
# MATCH
# =========================================================
def score_linha(desc_item, marca_item, produto_base, marca_base):
    s_desc = fuzz.token_set_ratio(desc_item, produto_base)
    s_marca = fuzz.ratio(marca_item, marca_base) if marca_item and marca_base else 0
    return (s_desc * 0.80) + (s_marca * 0.20)


def filtrar_ativos(base_df):
    if "situacao_norm" not in base_df.columns:
        return base_df

    ativos = base_df[
        base_df["situacao_norm"].astype(str).str.contains(
            "ATIV|VALID|REGULAR|VIGENTE", na=False, regex=True
        )
    ]

    return ativos if not ativos.empty else base_df


def melhor_match(desc_item, marca_item, base_df):
    desc_item = limpar_desc(desc_item)
    marca_item = normalizar_texto(marca_item)

    if not desc_item:
        return None

    candidatos = filtrar_ativos(base_df).copy()

    palavras = [p for p in desc_item.split() if len(p) >= 3]

    if palavras:
        mask = candidatos["produto_apresentacao"].astype(str).apply(
            lambda x: sum(1 for p in palavras if p in x) >= max(1, min(3, len(palavras) // 3 + 1))
        )
        filtrados = candidatos[mask]
        if not filtrados.empty:
            candidatos = filtrados

    if candidatos.empty:
        return None

    melhor = None
    melhor_score = -1

    for _, row in candidatos.iterrows():
        sc = score_linha(
            desc_item=desc_item,
            marca_item=marca_item,
            produto_base=row.get("produto_apresentacao", ""),
            marca_base=row.get("marca_norm", ""),
        )
        if sc > melhor_score:
            melhor_score = sc
            melhor = row

    if melhor is None:
        return None

    score_final = round(melhor_score, 2)

    # trava mínima para reduzir falso positivo
    if score_final < 70:
        return None

    return {
        "registro": melhor.get("registro_dig", ""),
        "marca_base": melhor.get("marca", ""),
        "situacao": melhor.get("situacao", ""),
        "score": score_final,
    }


def buscar_registro(desc_item, marca_item, med_df, prod_df):
    # 1) tenta medicamento
    if parece_registravel(desc_item):
        med = melhor_match(desc_item, marca_item, med_df)
        if med and med["registro"]:
            return {"fonte": "MEDICAMENTO", **med}

    # 2) tenta produto para saúde
    prod = melhor_match(desc_item, marca_item, prod_df)
    if prod and prod["registro"]:
        return {"fonte": "PRODUTO_SAUDE", **prod}

    # 3) fallback medicamento
    med2 = melhor_match(desc_item, marca_item, med_df)
    if med2 and med2["registro"]:
        return {"fonte": "MEDICAMENTO_FALLBACK", **med2}

    return None


# =========================================================
# PROCESSAMENTO EXCEL
# =========================================================
def processar_excel(workbook_bytes, lotes_alvo, med_df, prod_df, trocar_marca=True, modo_conferencia=False):
    wb = load_workbook(io.BytesIO(workbook_bytes))
    auditoria = []

    for aba in wb.sheetnames:
        if aba not in lotes_alvo:
            continue

        ws = wb[aba]
        header_row = achar_linha_cabecalho(ws)

        if not header_row:
            auditoria.append({
                "aba": aba,
                "linha": "",
                "item": "",
                "descricao": "",
                "marca_original": "",
                "marca_final": "",
                "registro_encontrado": "",
                "registro_planilha": "",
                "status": "Cabeçalho não identificado",
                "score": "",
                "fonte": "",
            })
            continue

        col_anvisa, _ = inserir_coluna_anvisa(ws, header_row)
        mapa = mapear_colunas(ws, header_row)

        if col_anvisa is None:
            auditoria.append({
                "aba": aba,
                "linha": "",
                "item": "",
                "descricao": "",
                "marca_original": "",
                "marca_final": "",
                "registro_encontrado": "",
                "registro_planilha": "",
                "status": "Não foi possível inserir/achar a coluna ANVISA",
                "score": "",
                "fonte": "",
            })
            continue

        mapa = mapear_colunas(ws, header_row)

        col_item = mapa.get("ITEM")
        col_desc = mapa.get("DESCRICAO")
        col_marca = mapa.get("MARCA")
        col_un = mapa.get("UN")
        col_anvisa = mapa.get("ANVISA")

        if not col_desc or not col_marca or not col_un or not col_anvisa:
            auditoria.append({
                "aba": aba,
                "linha": "",
                "item": "",
                "descricao": "",
                "marca_original": "",
                "marca_final": "",
                "registro_encontrado": "",
                "registro_planilha": "",
                "status": "Colunas essenciais ausentes",
                "score": "",
                "fonte": "",
            })
            continue

        for r in range(header_row + 1, ws.max_row + 1):
            item = ws.cell(r, col_item).value if col_item else None
            desc = ws.cell(r, col_desc).value
            marca_original = ws.cell(r, col_marca).value
            reg_planilha = ws.cell(r, col_anvisa).value

            if eh_linha_vazia_ou_total(desc):
                continue

            resultado = buscar_registro(desc, marca_original, med_df, prod_df)

            if resultado:
                registro_encontrado = resultado["registro"]
                marca_sugerida = resultado["marca_base"]
                score = resultado["score"]
                fonte = resultado["fonte"]

                if modo_conferencia:
                    status = (
                        "CONFERE"
                        if apenas_digitos(reg_planilha) == registro_encontrado
                        else "DIVERGENTE"
                    )

                else:
                    ws.cell(r, col_anvisa).value = registro_encontrado
                    ws.cell(r, col_anvisa).fill = FILL_OK
                    status = "PREENCHIDO"

                    if trocar_marca:
                        marca_atual_norm = normalizar_texto(marca_original)
                        marca_nova_norm = normalizar_texto(marca_sugerida)

                        if marca_nova_norm and marca_nova_norm != marca_atual_norm:
                            ws.cell(r, col_marca).value = marca_sugerida
                            ws.cell(r, col_marca).fill = FILL_ALTERADO
                            status = "PREENCHIDO + MARCA AJUSTADA"

                auditoria.append({
                    "aba": aba,
                    "linha": r,
                    "item": item,
                    "descricao": desc,
                    "marca_original": marca_original,
                    "marca_final": marca_sugerida if marca_sugerida else marca_original,
                    "registro_encontrado": registro_encontrado,
                    "registro_planilha": apenas_digitos(reg_planilha),
                    "status": status,
                    "score": score,
                    "fonte": fonte,
                })

            else:
                auditoria.append({
                    "aba": aba,
                    "linha": r,
                    "item": item,
                    "descricao": desc,
                    "marca_original": marca_original,
                    "marca_final": marca_original,
                    "registro_encontrado": "",
                    "registro_planilha": apenas_digitos(reg_planilha),
                    "status": "NAO ENCONTRADO",
                    "score": "",
                    "fonte": "",
                })

    if "AUDITORIA_ANVISA" in wb.sheetnames:
        del wb["AUDITORIA_ANVISA"]

    ws_aud = wb.create_sheet("AUDITORIA_ANVISA")
    headers = [
        "aba", "linha", "item", "descricao",
        "marca_original", "marca_final",
        "registro_encontrado", "registro_planilha",
        "status", "score", "fonte"
    ]

    for c, h in enumerate(headers, 1):
        ws_aud.cell(1, c).value = h
        ws_aud.cell(1, c).fill = FILL_HEADER

    for i, row in enumerate(auditoria, start=2):
        for c, h in enumerate(headers, 1):
            ws_aud.cell(i, c).value = row.get(h, "")

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    df_aud = pd.DataFrame(auditoria)
    return output, df_aud


# =========================================================
# CONFERÊNCIA PDF (BÁSICA)
# =========================================================
def extrair_linhas_pdf(pdf_bytes):
    linhas = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pagina_idx, pagina in enumerate(pdf.pages, start=1):
            texto = pagina.extract_text() or ""
            for linha in texto.splitlines():
                linha_limpa = linha.strip()
                if linha_limpa:
                    linhas.append({
                        "pagina": pagina_idx,
                        "linha_pdf": linha_limpa
                    })

    return pd.DataFrame(linhas)


def conferir_pdf(pdf_bytes, med_df, prod_df):
    linhas_df = extrair_linhas_pdf(pdf_bytes)
    resultados = []

    if linhas_df.empty:
        return pd.DataFrame([{
            "pagina": "",
            "linha_pdf": "",
            "descricao_identificada": "",
            "registro_encontrado": "",
            "status": "PDF sem texto extraível"
        }])

    padrao_reg = re.compile(r"\b\d{9,13}\b")

    for _, row in linhas_df.iterrows():
        linha = row["linha_pdf"]
        pagina = row["pagina"]

        if len(linha) < 8:
            continue

        registro_existente = ""
        m = padrao_reg.search(linha)
        if m:
            registro_existente = m.group(0)

        if not parece_registravel(linha):
            continue

        encontrado = buscar_registro(linha, "", med_df, prod_df)

        if encontrado:
            reg = encontrado["registro"]
            status = "CONFERE" if registro_existente and registro_existente == reg else "LOCALIZADO"
            if registro_existente and registro_existente != reg:
                status = "DIVERGENTE"
            resultados.append({
                "pagina": pagina,
                "linha_pdf": linha,
                "descricao_identificada": linha,
                "registro_encontrado": reg,
                "registro_existente_pdf": registro_existente,
                "status": status,
                "score": encontrado["score"],
                "fonte": encontrado["fonte"],
            })

    if not resultados:
        return pd.DataFrame([{
            "pagina": "",
            "linha_pdf": "",
            "descricao_identificada": "",
            "registro_encontrado": "",
            "registro_existente_pdf": "",
            "status": "Nenhuma linha aproveitável encontrada no PDF"
        }])

    return pd.DataFrame(resultados)


# =========================================================
# INTERFACE
# =========================================================
st.title("ANVISA - preenchimento e conferência por lotes")
st.write(
    "Este sistema processa planilhas com múltiplas abas, trabalha apenas com os lotes escolhidos "
    "e insere/preenche a coluna **Nº REGISTRO NA ANVISA** quando ela não existir."
)

with st.sidebar:
    st.subheader("Bases da ANVISA")
    st.caption("Você pode usar upload manual dos CSVs ou deixar os arquivos na pasta data/ do projeto.")

    arquivo_med_sidebar = st.file_uploader(
        "Upload base de medicamentos (.csv)",
        type=["csv"],
        key="med_sidebar"
    )

    arquivo_prod_sidebar = st.file_uploader(
        "Upload base de produtos para saúde (.csv)",
        type=["csv"],
        key="prod_sidebar"
    )

    st.markdown("---")
    st.subheader("Configuração")
    lotes_escolhidos = st.multiselect(
        "Lotes a processar",
        options=LOTES_PADRAO,
        default=LOTES_PADRAO
    )

    trocar_marca = st.checkbox(
        "Trocar MARCA se a marca da base ativa for diferente",
        value=True
    )

modo = st.radio(
    "Escolha o modo",
    ["Preencher Excel", "Conferir Excel", "Conferir PDF"],
    horizontal=True
)

if modo in ("Preencher Excel", "Conferir Excel"):
    arquivo_principal = st.file_uploader("Envie a planilha Excel (.xlsx)", type=["xlsx"])
else:
    arquivo_principal = st.file_uploader("Envie o PDF para conferência (.pdf)", type=["pdf"])

if st.button("Executar"):
    try:
        med_df, prod_df = carregar_bases(
            arquivo_med_upload=arquivo_med_sidebar,
            arquivo_prod_upload=arquivo_prod_sidebar
        )

        if arquivo_principal is None:
            st.error("Envie o arquivo principal antes de executar.")
            st.stop()

        if modo == "Preencher Excel":
            saida, aud = processar_excel(
                workbook_bytes=arquivo_principal.getvalue(),
                lotes_alvo=lotes_escolhidos,
                med_df=med_df,
                prod_df=prod_df,
                trocar_marca=trocar_marca,
                modo_conferencia=False,
            )

            st.success("Processamento concluído.")
            st.dataframe(aud, use_container_width=True)

            st.download_button(
                "Baixar planilha processada",
                data=saida.getvalue(),
                file_name="planilha_processada_anvisa.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            st.download_button(
                "Baixar auditoria CSV",
                data=aud.to_csv(index=False).encode("utf-8-sig"),
                file_name="auditoria_anvisa.csv",
                mime="text/csv"
            )

        elif modo == "Conferir Excel":
            _, aud = processar_excel(
                workbook_bytes=arquivo_principal.getvalue(),
                lotes_alvo=lotes_escolhidos,
                med_df=med_df,
                prod_df=prod_df,
                trocar_marca=False,
                modo_conferencia=True,
            )

            st.success("Conferência da planilha concluída.")
            st.dataframe(aud, use_container_width=True)

            st.download_button(
                "Baixar relatório de conferência",
                data=aud.to_csv(index=False).encode("utf-8-sig"),
                file_name="conferencia_excel_anvisa.csv",
                mime="text/csv"
            )

        elif modo == "Conferir PDF":
            conf_pdf = conferir_pdf(
                pdf_bytes=arquivo_principal.getvalue(),
                med_df=med_df,
                prod_df=prod_df
            )

            st.success("Conferência do PDF concluída.")
            st.dataframe(conf_pdf, use_container_width=True)

            st.download_button(
                "Baixar relatório do PDF",
                data=conf_pdf.to_csv(index=False).encode("utf-8-sig"),
                file_name="conferencia_pdf_anvisa.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Erro: {e}")
