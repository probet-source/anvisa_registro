from __future__ import annotations

import io
import re
import unicodedata
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd
import requests
import streamlit as st
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

st.set_page_config(page_title="Validador ANVISA para Planilhas", page_icon="💊", layout="wide")

MED_URL = "https://dados.anvisa.gov.br/dados/CONSULTAS/PRODUTOS/TA_CONSULTA_MEDICAMENTOS.CSV"
SAUDE_URL = "https://dados.anvisa.gov.br/dados/CONSULTAS/PRODUTOS/TA_CONSULTA_PRODUTOS_SAUDE.CSV"

LOTES_MED = {"L01", "L02", "L06", "L07", "L08"}
LOTES_SAUDE = {"L03", "L04", "L05"}
ACTIVE_WORDS = {
    "ATIVO", "ATIVA", "VALIDO", "VÁLIDO", "REGULAR", "REGULARIZADO", "REGISTRADO", "CADASTRADO"
}

STOPWORDS = {
    "DE", "DA", "DO", "DAS", "DOS", "E", "EM", "COM", "PARA", "POR", "P", "PX", "PCT", "CX", "UND",
    "UNID", "FR", "AMP", "AMPOLA", "AMPOLA(S)", "ML", "MG", "MCG", "G", "KG", "UI", "PO", "SOL",
    "SOLUCAO", "SOLUÇÃO", "SUSP", "ORAL", "INJ", "INJETAVEL", "INJETÁVEL", "COMP", "COMPRIMIDO", "COMPRIMIDOS",
    "CAP", "CAPS", "CAPSULA", "CAPSULAS", "BISNAGA", "FRASCO", "TUBO", "BOLSA", "SERINGA", "SERINGAS",
    "KIT", "AUTOCLAVAVEL", "AUTOCLAVÁVEL", "COR", "TAM", "ESTERIL", "ESTÉRIL", "DESCARTAVEL", "DESCARTÁVEL", "C", "X"
}

HIGHLIGHT_FILL = PatternFill(fill_type="solid", fgColor="FFF2CC")


@dataclass
class MatchResult:
    registro: str
    marca_final: str
    nome_anvisa: str
    situacao: str
    score: float
    fonte: str


def normalize(text) -> str:
    if text is None:
        return ""
    text = str(text).strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("º", "O").replace("°", "O")
    text = text.replace(",", ".")
    text = re.sub(r"[^A-Z0-9%+/., -]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def token_set(text: str) -> list[str]:
    toks = re.findall(r"[A-Z0-9%/.+-]+", normalize(text))
    return [t for t in toks if t not in STOPWORDS and len(t) > 1]


def similarity(a: str, b: str) -> float:
    a = normalize(a)
    b = normalize(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def choose_col(df: pd.DataFrame, include_terms: list[str], exclude_terms: list[str] | None = None):
    exclude_terms = exclude_terms or []
    candidates = []
    for col in df.columns:
        n = normalize(col)
        if all(term in n for term in include_terms) and not any(term in n for term in exclude_terms):
            candidates.append(col)
    if candidates:
        candidates.sort(key=lambda c: (len(c), c))
        return candidates[0]
    return None


def infer_columns_med(df: pd.DataFrame) -> dict:
    return {
        "produto": choose_col(df, ["PRODUTO"]) or choose_col(df, ["NOME", "PRODUTO"]) or choose_col(df, ["MEDICAMENTO"]),
        "empresa": choose_col(df, ["RAZAO", "SOCIAL"]) or choose_col(df, ["EMPRESA"]) or choose_col(df, ["DETENTOR"]) or choose_col(df, ["FABRICANTE"]),
        "apresentacao": choose_col(df, ["APRESENT"]) or choose_col(df, ["COMPLEMENTO"]) or choose_col(df, ["EMBALAGEM"]) or choose_col(df, ["FORMA"]),
        "registro": choose_col(df, ["REGISTRO"], ["PROCESSO", "DATA"]) or choose_col(df, ["NUMERO", "REGISTRO"], ["PROCESSO", "DATA"]) or choose_col(df, ["NUMERO", "REGULARIZ"]),
        "situacao": choose_col(df, ["SITUACAO"]) or choose_col(df, ["SITUAÇÃO"]) or choose_col(df, ["STATUS"]),
        "nome_comercial": choose_col(df, ["NOME", "COMERCIAL"]) or choose_col(df, ["MARCA"]),
    }


def infer_columns_saude(df: pd.DataFrame) -> dict:
    return {
        "produto": choose_col(df, ["NOME", "PRODUTO"]) or choose_col(df, ["PRODUTO"]),
        "empresa": choose_col(df, ["NOME", "EMPRESA"]) or choose_col(df, ["RAZAO", "SOCIAL"]) or choose_col(df, ["EMPRESA"]) or choose_col(df, ["DETENTOR"]),
        "apresentacao": choose_col(df, ["MODELO"]) or choose_col(df, ["NOME", "TECNICO"]) or choose_col(df, ["DESCR"]) or choose_col(df, ["APRESENT"]),
        "registro": choose_col(df, ["NUMERO", "REGISTRO"], ["PROCESSO", "DATA"]) or choose_col(df, ["REGISTRO"], ["PROCESSO", "DATA"]) or choose_col(df, ["NOTIFICACAO"]),
        "situacao": choose_col(df, ["SITUACAO"]) or choose_col(df, ["SITUAÇÃO"]) or choose_col(df, ["STATUS"]),
        "nome_comercial": choose_col(df, ["MARCA"]) or choose_col(df, ["NOME", "COMERCIAL"]),
    }


def read_csv_flexible(raw_bytes: bytes) -> pd.DataFrame:
    last_error = None
    for enc in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
        try:
            return pd.read_csv(io.BytesIO(raw_bytes), sep=";", quotechar='"', dtype=str, encoding=enc, low_memory=False, on_bad_lines="skip").fillna("")
        except Exception as exc:
            last_error = exc
    raise last_error


@st.cache_data(show_spinner=False)
def fetch_csv(url: str) -> bytes:
    response = requests.get(url, timeout=240)
    response.raise_for_status()
    return response.content


@st.cache_data(show_spinner=True)
def load_anvisa_bases() -> dict:
    med = read_csv_flexible(fetch_csv(MED_URL))
    saude = read_csv_flexible(fetch_csv(SAUDE_URL))

    med_cols = infer_columns_med(med)
    saude_cols = infer_columns_saude(saude)

    med = filter_active(med, med_cols)
    saude = filter_active(saude, saude_cols)

    med["_blob"] = med.apply(lambda row: build_blob(row, med_cols), axis=1)
    saude["_blob"] = saude.apply(lambda row: build_blob(row, saude_cols), axis=1)

    return {
        "med": med,
        "saude": saude,
        "med_cols": med_cols,
        "saude_cols": saude_cols,
    }


def build_blob(row: pd.Series, cols: dict) -> str:
    parts = []
    for key in ("produto", "apresentacao", "empresa", "nome_comercial", "situacao"):
        col = cols.get(key)
        if col and col in row:
            parts.append(str(row[col]))
    return " | ".join([p for p in parts if p])


def is_active_value(value: str) -> bool:
    n = normalize(value)
    if not n:
        return True
    if any(w in n for w in ACTIVE_WORDS):
        return True
    if "CANCEL" in n or "VENCID" in n or "INATIV" in n or "SUSPENS" in n or "CADUC" in n:
        return False
    return True


def filter_active(df: pd.DataFrame, cols: dict) -> pd.DataFrame:
    situ_col = cols.get("situacao")
    if not situ_col or situ_col not in df.columns:
        return df.copy()
    mask = df[situ_col].astype(str).apply(is_active_value)
    filtered = df.loc[mask].copy()
    return filtered if not filtered.empty else df.copy()


def extract_core_tokens(desc: str) -> list[str]:
    return token_set(desc)[:14]


def extract_measures(text: str) -> list[str]:
    text = normalize(text)
    patterns = [
        r"\b\d+(?:\.\d+)?\s*(?:MG|ML|MCG|G|UI|%)\b",
        r"\b\d+(?:\.\d+)?\s*MG/ML\b",
        r"\b\d+(?:\.\d+)?\s*ML\b",
        r"\b\d+(?:\.\d+)?\s*G\b",
    ]
    found = []
    for pat in patterns:
        found.extend(re.findall(pat, text))
    seen = []
    for item in found:
        if item not in seen:
            seen.append(item)
    return seen


def candidate_score(desc: str, marca_atual: str, row: pd.Series, cols: dict) -> float:
    produto = str(row.get(cols.get("produto", ""), ""))
    empresa = str(row.get(cols.get("empresa", ""), ""))
    apresent = str(row.get(cols.get("apresentacao", ""), ""))
    nome_comercial = str(row.get(cols.get("nome_comercial", ""), ""))
    situacao = str(row.get(cols.get("situacao", ""), ""))

    blob = " ".join([produto, apresent, empresa, nome_comercial, situacao])
    desc_n = normalize(desc)
    marca_n = normalize(marca_atual)
    blob_n = normalize(blob)
    empresa_n = normalize(empresa)
    nome_comercial_n = normalize(nome_comercial)

    score = 0.0

    score += 45 * similarity(desc_n, blob_n)

    dtoks = set(extract_core_tokens(desc))
    btoks = set(token_set(blob))
    if dtoks:
        inter = len(dtoks & btoks)
        score += min(30, inter * 3.75)

    for measure in extract_measures(desc):
        if measure in blob_n:
            score += 6

    if marca_n:
        if marca_n and empresa_n and marca_n in empresa_n:
            score += 24
        elif marca_n and nome_comercial_n and marca_n in nome_comercial_n:
            score += 24
        else:
            score += 10 * max(similarity(marca_n, empresa_n), similarity(marca_n, nome_comercial_n))

    if is_active_value(situacao):
        score += 8

    return score


def shortlist_candidates(df: pd.DataFrame, cols: dict, desc: str, marca_atual: str) -> pd.DataFrame:
    tokens = extract_core_tokens(desc)
    if not tokens:
        subset = df.copy()
    else:
        mask = pd.Series(False, index=df.index)
        blob_series = df["_blob"].astype(str).map(normalize)
        for tok in tokens[:8]:
            mask = mask | blob_series.str.contains(re.escape(tok), regex=True)
        subset = df.loc[mask].copy()
        if subset.empty:
            subset = df.copy()

    subset["_score"] = subset.apply(lambda row: candidate_score(desc, marca_atual, row, cols), axis=1)
    subset = subset.sort_values("_score", ascending=False).head(40).copy()
    return subset


def choose_best_match(df: pd.DataFrame, cols: dict, desc: str, marca_atual: str, threshold: float) -> MatchResult | None:
    subset = shortlist_candidates(df, cols, desc, marca_atual)
    if subset.empty:
        return None

    best = subset.iloc[0]
    if float(best["_score"]) < threshold:
        return None

    registro = clean_registro(best.get(cols.get("registro", ""), ""))
    empresa = compact_spaces(str(best.get(cols.get("empresa", ""), "")))
    nome_produto = compact_spaces(str(best.get(cols.get("produto", ""), "")))
    situacao = compact_spaces(str(best.get(cols.get("situacao", ""), "")))

    return MatchResult(
        registro=registro,
        marca_final=empresa or compact_spaces(marca_atual),
        nome_anvisa=nome_produto,
        situacao=situacao,
        score=float(best["_score"]),
        fonte="ANVISA",
    )


def clean_registro(value: str) -> str:
    value = re.sub(r"\D", "", str(value or ""))
    return value


def find_header_row(ws) -> int | None:
    for r in range(1, min(ws.max_row, 15) + 1):
        row_vals = [normalize(ws.cell(r, c).value) for c in range(1, min(ws.max_column, 12) + 1)]
        joined = " | ".join(row_vals)
        if "DESCRICAO" in joined and "MARCA" in joined and "UN" in joined:
            return r
    return None


def find_col_indices(ws, header_row: int) -> dict:
    out = {}
    for c in range(1, ws.max_column + 1):
        value = normalize(ws.cell(header_row, c).value)
        if value == "ITEM":
            out["item"] = c
        elif "DESCRICAO" in value:
            out["descricao"] = c
        elif value == "MARCA":
            out["marca"] = c
        elif value in {"UN", "UND"}:
            out["un"] = c
        elif "N REGISTRO NA ANVISA" in value or "NO REGISTRO NA ANVISA" in value:
            out["anvisa"] = c
    return out


def ensure_anvisa_column(ws, header_row: int, col_map: dict) -> dict:
    if "anvisa" in col_map:
        return col_map

    marca_col = col_map["marca"]
    un_col = col_map["un"]
    ws.insert_cols(un_col)
    src_col = marca_col
    new_col = marca_col + 1

    for r in range(1, ws.max_row + 1):
        src = ws.cell(r, src_col)
        dst = ws.cell(r, new_col)
        if src.has_style:
            dst._style = copy(src._style)
        if src.number_format:
            dst.number_format = src.number_format
        if src.font:
            dst.font = copy(src.font)
        if src.fill:
            dst.fill = copy(src.fill)
        if src.border:
            dst.border = copy(src.border)
        if src.alignment:
            dst.alignment = copy(src.alignment)
        if src.protection:
            dst.protection = copy(src.protection)

    ws.cell(header_row, new_col).value = "Nº REGISTRO NA ANVISA"
    return find_col_indices(ws, header_row)


def update_workbook(uploaded_file, data: dict, threshold: float = 54.0):
    uploaded_file.seek(0)
    wb = load_workbook(uploaded_file)
    audit_rows = []

    for sheet_name in wb.sheetnames:
        if sheet_name not in LOTES_MED | LOTES_SAUDE:
            continue
        ws = wb[sheet_name]
        header_row = find_header_row(ws)
        if not header_row:
            continue
        col_map = find_col_indices(ws, header_row)
        required = {"descricao", "marca", "un"}
        if not required.issubset(set(col_map)):
            continue
        col_map = ensure_anvisa_column(ws, header_row, col_map)

        base_df = data["med"] if sheet_name in LOTES_MED else data["saude"]
        cols = data["med_cols"] if sheet_name in LOTES_MED else data["saude_cols"]

        for r in range(header_row + 1, ws.max_row + 1):
            item = ws.cell(r, col_map.get("item", 1)).value
            descricao = ws.cell(r, col_map["descricao"]).value
            marca_atual = ws.cell(r, col_map["marca"]).value

            if item in (None, "") or descricao in (None, ""):
                continue

            result = choose_best_match(base_df, cols, str(descricao), str(marca_atual or ""), threshold)
            if not result:
                audit_rows.append({
                    "aba": sheet_name,
                    "linha": r,
                    "item": item,
                    "descricao": descricao,
                    "marca_original": marca_atual,
                    "marca_final": marca_atual,
                    "registro_anvisa": "",
                    "situacao": "NÃO LOCALIZADO",
                    "score": 0,
                    "observacao": "Sem correspondência segura acima do limiar",
                })
                continue

            old_brand = compact_spaces(str(marca_atual or ""))
            new_brand = compact_spaces(result.marca_final)
            changed_brand = normalize(old_brand) != normalize(new_brand) and new_brand != ""

            ws.cell(r, col_map["anvisa"]).value = result.registro
            if changed_brand:
                ws.cell(r, col_map["marca"]).value = new_brand
                ws.cell(r, col_map["marca"]).fill = HIGHLIGHT_FILL
            ws.cell(r, col_map["anvisa"]).fill = HIGHLIGHT_FILL

            audit_rows.append({
                "aba": sheet_name,
                "linha": r,
                "item": item,
                "descricao": descricao,
                "marca_original": old_brand,
                "marca_final": new_brand or old_brand,
                "registro_anvisa": result.registro,
                "situacao": result.situacao or "ATIVO/REGULAR",
                "score": round(result.score, 2),
                "observacao": "Marca ajustada para detentor ativo" if changed_brand else "Marca mantida; registro confirmado",
            })

    if "AUDITORIA_ANVISA" in wb.sheetnames:
        del wb["AUDITORIA_ANVISA"]
    audit_ws = wb.create_sheet("AUDITORIA_ANVISA")
    cols = [
        "aba", "linha", "item", "descricao", "marca_original", "marca_final",
        "registro_anvisa", "situacao", "score", "observacao"
    ]
    audit_ws.append(cols)
    for row in audit_rows:
        audit_ws.append([row.get(c, "") for c in cols])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    audit_df = pd.DataFrame(audit_rows)
    return output, audit_df


def main():
    st.title("Validador de marcas ativas e registros ANVISA")
    st.write(
        "Envie uma planilha Excel. O sistema confere a marca sugerida, troca por uma marca/detentor ativo quando necessário "
        "e preenche a coluna **Nº REGISTRO NA ANVISA** com base nas bases públicas da ANVISA."
    )

    with st.expander("Como funciona"):
        st.markdown(
            """
            1. Baixa as bases oficiais públicas da ANVISA.  
            2. Filtra registros com situação ativa/válida/regular.  
            3. Compara descrição do item + marca sugerida da planilha.  
            4. Se a marca não estiver ativa, substitui por uma marca/detentor ativo compatível.  
            5. Preenche o número do registro e gera uma aba de auditoria.
            """
        )

    threshold = st.slider("Limiar mínimo de confiança", 40.0, 90.0, 54.0, 1.0)
    arquivo = st.file_uploader("Selecione a planilha .xlsx", type=["xlsx"])

    if st.button("Processar planilha", type="primary", disabled=arquivo is None):
        with st.spinner("Baixando e preparando bases da ANVISA..."):
            data = load_anvisa_bases()
        with st.spinner("Conferindo marcas ativas e preenchendo registros..."):
            resultado_excel, audit_df = update_workbook(arquivo, data, threshold=threshold)

        nome_saida = Path(arquivo.name).stem + "_ANVISA_VALIDADA.xlsx"
        csv_bytes = audit_df.to_csv(index=False).encode("utf-8-sig")

        total = len(audit_df)
        localizados = int((audit_df["registro_anvisa"].fillna("") != "").sum()) if not audit_df.empty else 0
        marcas_trocadas = int((audit_df["marca_original"].fillna("") != audit_df["marca_final"].fillna("")).sum()) if not audit_df.empty else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Itens analisados", total)
        c2.metric("Registros encontrados", localizados)
        c3.metric("Marcas ajustadas", marcas_trocadas)

        st.download_button(
            "Baixar planilha validada",
            data=resultado_excel.getvalue(),
            file_name=nome_saida,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "Baixar relatório de auditoria (CSV)",
            data=csv_bytes,
            file_name="auditoria_anvisa.csv",
            mime="text/csv",
        )

        st.subheader("Prévia da auditoria")
        st.dataframe(audit_df.head(200), use_container_width=True)


if __name__ == "__main__":
    main()
