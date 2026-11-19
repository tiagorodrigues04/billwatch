"""Leitura e limpeza de extratos bancários.

Os bancos portugueses exportam extratos em formatos diferentes:
- separador ';' ou ','
- números com vírgula decimal ("1.234,56") ou ponto ("1234.56")
- uma coluna "Montante" com sinal, ou duas colunas "Débito" / "Crédito"
- datas em "dd-mm-aaaa", "dd/mm/aaaa" ou "aaaa-mm-dd"

Este módulo transforma qualquer um desses formatos numa tabela padrão com
três colunas: data (datetime), descricao (texto) e valor (float, negativo = saída).
"""

from __future__ import annotations

import io
import re
import unicodedata

import pandas as pd

# Palavras que costumam aparecer no nome de cada coluna, em PT e EN.
NOMES_DATA = ["data mov", "data valor", "data", "date", "dia"]
NOMES_DESCRICAO = ["descri", "movimento", "description", "detalhe", "concept", "referencia"]
NOMES_VALOR = ["montante", "valor", "amount", "importancia", "quantia"]
NOMES_DEBITO = ["debito", "debit", "saida"]
NOMES_CREDITO = ["credito", "credit", "entrada"]


def _sem_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c))


def _chave(nome_coluna: str) -> str:
    return _sem_acentos(nome_coluna).lower().strip()


def _encontrar_coluna(colunas: list[str], candidatos: list[str], excluir: set[str] = frozenset()) -> str | None:
    """Devolve a primeira coluna cujo nome contém um dos candidatos (por ordem de prioridade)."""
    for candidato in candidatos:
        for coluna in colunas:
            if coluna in excluir:
                continue
            if candidato in _chave(coluna):
                return coluna
    return None


def converter_numero(valor) -> float | None:
    """Converte "1.234,56", "-12,99", "12.99", "€ 7,99" ou 7.99 num float."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "")
    if not texto:
        return None
    negativo = texto.startswith("-") or (texto.startswith("(") and texto.endswith(")"))
    texto = texto.strip("-+()")
    if "," in texto and "." in texto:
        # O separador que aparece por último é o decimal.
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        numero = float(texto)
    except ValueError:
        return None
    return -numero if negativo else numero


def _ler_csv(conteudo: bytes) -> pd.DataFrame:
    """Tenta várias codificações e separadores até obter uma tabela com 3+ colunas."""
    for codificacao in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
        linhas = texto.splitlines()
        # Alguns bancos põem linhas de cabeçalho (nome, IBAN...) antes da tabela:
        # procuramos a primeira linha que parece ter nomes de colunas.
        inicio = 0
        for i, linha in enumerate(linhas[:30]):
            chave = _chave(linha)
            if any(n in chave for n in NOMES_DATA) and (
                any(n in chave for n in NOMES_VALOR + NOMES_DEBITO)
            ):
                inicio = i
                break
        corpo = "\n".join(linhas[inicio:])
        for separador in (";", ",", "\t"):
            try:
                df = pd.read_csv(io.StringIO(corpo), sep=separador, dtype=str)
            except Exception:
                continue
            if df.shape[1] >= 3:
                return df
    raise ValueError("Não consegui ler o ficheiro. Confirma que é um CSV exportado do banco.")


def normalizar_extrato(df: pd.DataFrame) -> pd.DataFrame:
    """Converte uma tabela de extrato qualquer no formato padrão (data, descricao, valor)."""
    colunas = [str(c) for c in df.columns]
    df = df.copy()
    df.columns = colunas

    col_data = _encontrar_coluna(colunas, NOMES_DATA)
    # Colunas de datas e de saldo nunca são o valor do movimento ("Data Valor" engana!).
    nao_valor = {c for c in colunas if any(n in _chave(c) for n in ("data", "date", "saldo", "balance"))}
    col_desc = _encontrar_coluna(colunas, NOMES_DESCRICAO, excluir=nao_valor)
    excluir = nao_valor | {col_desc}
    col_valor = _encontrar_coluna(colunas, NOMES_VALOR, excluir=excluir)
    col_debito = _encontrar_coluna(colunas, NOMES_DEBITO, excluir=excluir)
    col_credito = _encontrar_coluna(colunas, NOMES_CREDITO, excluir=excluir)

    if col_data is None or col_desc is None:
        raise ValueError(f"Não encontrei as colunas de data e descrição. Colunas lidas: {colunas}")

    if col_valor is not None:
        valores = df[col_valor].map(converter_numero)
    elif col_debito is not None:
        debitos = df[col_debito].map(converter_numero).fillna(0).abs()
        creditos = df[col_credito].map(converter_numero).fillna(0).abs() if col_credito else 0
        valores = creditos - debitos
    else:
        raise ValueError(f"Não encontrei a coluna do valor. Colunas lidas: {colunas}")

    resultado = pd.DataFrame(
        {
            "data": pd.to_datetime(df[col_data], dayfirst=True, errors="coerce", format="mixed"),
            "descricao": df[col_desc].astype(str).str.strip(),
            "valor": valores.astype(float),
        }
    )
    resultado = resultado.dropna(subset=["data", "valor"])
    return resultado.sort_values("data").reset_index(drop=True)


def _linha_e_cabecalho(valores) -> bool:
    chave = _chave(" ".join(str(v) for v in valores if pd.notna(v)))
    return any(n in chave for n in NOMES_DATA) and any(n in chave for n in NOMES_VALOR + NOMES_DEBITO)


def _tabela_com_cabecalho(bruto: pd.DataFrame) -> pd.DataFrame:
    """Numa folha lida sem cabeçalho, encontra a linha dos nomes das colunas e corta o que está antes."""
    for i in range(min(len(bruto), 40)):
        if _linha_e_cabecalho(bruto.iloc[i].tolist()):
            tabela = bruto.iloc[i + 1:].copy()
            tabela.columns = [str(c).strip() for c in bruto.iloc[i].tolist()]
            tabela = tabela.loc[:, [c not in ("nan", "None", "") for c in tabela.columns]]
            return tabela.dropna(how="all")
    raise ValueError("Não encontrei a linha com os nomes das colunas (Data, Descrição, Valor...).")


def _ler_excel(conteudo: bytes) -> pd.DataFrame:
    """Lê .xlsx/.xls. Alguns bancos dão um '.xls' que na verdade é uma página HTML com uma tabela."""
    inicio = conteudo[:200].lstrip().lower()
    if inicio.startswith(b"<"):
        try:
            texto = conteudo.decode("utf-8")
        except UnicodeDecodeError:
            texto = conteudo.decode("latin-1")
        tabelas = pd.read_html(io.StringIO(texto), thousands=None, decimal=",")
        for tabela in sorted(tabelas, key=len, reverse=True):
            # O pandas pode já ter usado uma linha como cabeçalho; voltamos a pô-la como dados
            # para que _tabela_com_cabecalho a encontre como em qualquer outro formato.
            cabecalho = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in tabela.columns]
            bruto = pd.DataFrame([cabecalho] + tabela.values.tolist())
            try:
                return _tabela_com_cabecalho(bruto)
            except ValueError:
                continue
        raise ValueError("Não encontrei a tabela de movimentos no ficheiro.")
    motor = "openpyxl" if conteudo[:2] == b"PK" else "xlrd"
    folhas = pd.read_excel(io.BytesIO(conteudo), header=None, sheet_name=None, engine=motor)
    for bruto in folhas.values():
        try:
            return _tabela_com_cabecalho(bruto)
        except ValueError:
            continue
    raise ValueError("Não encontrei a tabela de movimentos em nenhuma folha do Excel.")


def carregar_extrato(conteudo: bytes, nome: str = "") -> pd.DataFrame:
    """Ponto de entrada: recebe os bytes do ficheiro (CSV, Excel ou PDF) e devolve o extrato normalizado."""
    nome = nome.lower()
    if nome.endswith(".pdf") or conteudo[:4] == b"%PDF":
        return ler_extrato_pdf(conteudo)
    assinatura_excel = conteudo[:2] == b"PK" or conteudo[:4] == b"\xd0\xcf\x11\xe0"
    if nome.endswith((".xlsx", ".xls")) or assinatura_excel:
        return normalizar_extrato(_ler_excel(conteudo))
    return normalizar_extrato(_ler_csv(conteudo))


def juntar_extratos(extratos: list[pd.DataFrame]) -> pd.DataFrame:
    """Junta vários extratos (ex.: um por mês) num só, sem contar movimentos repetidos.

    Se dois ficheiros se sobrepõem (ex.: ambos têm o dia 1 de março), os movimentos
    desses dias aparecem nos dois. Não podemos simplesmente apagar linhas iguais,
    porque dois cafés de 1,20€ no mesmo dia são mesmo dois movimentos. Por isso
    numeramos as repetições dentro de cada ficheiro (1.º café, 2.º café...) e só
    apagamos quando o mesmo movimento com o mesmo número aparece noutro ficheiro.
    """
    if not extratos:
        return pd.DataFrame(columns=["data", "descricao", "valor"])
    partes = []
    for df in extratos:
        df = df.copy()
        df["_ocorrencia"] = df.groupby(["data", "descricao", "valor"]).cumcount()
        partes.append(df)
    junto = pd.concat(partes, ignore_index=True)
    junto = junto.drop_duplicates(subset=["data", "descricao", "valor", "_ocorrencia"])
    return junto.drop(columns="_ocorrencia").sort_values("data").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Normalização dos nomes dos comerciantes
# ---------------------------------------------------------------------------

# Prefixos que os bancos acrescentam à descrição e que não identificam o comerciante.
_RUIDO = re.compile(
    r"\b(COMPRA|COMPRAS|PAG(AMENTO)?|PAGTO|DD|DEB(ITO)?|DIRECTO|DIRETO|TRF|TRANSF(ERENCIA)?|"
    r"MB ?WAY|MBWAY|CARTAO|CARD|CONTACTLESS|ONLINE|WWW|COM|PT|LDA|SA|S A|REF|N|NO|ENT|"
    r"PORTUGAL|LISBOA|PORTO|COIMBRA|EUR|VISA|MASTERCARD|APPLE PAY|GOOGLE PAY)\b"
)


def chave_comerciante(descricao: str) -> str:
    """Reduz uma descrição bancária a uma chave estável.

    "COMPRA 4521 NETFLIX.COM 866-579 12/03" -> "NETFLIX"
    "DD EDP COMERCIAL REF 123456789"       -> "EDP COMERCIAL"
    """
    texto = _sem_acentos(descricao).upper()
    texto = re.sub(r"[^A-Z0-9 ]", " ", texto)       # pontuação fora
    texto = re.sub(r"\b\w*\d\w*\b", " ", texto)       # tokens com números (refs, datas, cartões)
    texto = _RUIDO.sub(" ", texto)
    tokens = [t for t in texto.split() if len(t) > 1]
    return " ".join(tokens[:2]) if tokens else _sem_acentos(descricao).upper().strip()


# ---------------------------------------------------------------------------
# Extratos em PDF
# ---------------------------------------------------------------------------

_DATA = r"\d{2}[-/.]\d{2}[-/.](?:\d{4}|\d{2})"
_VALOR = r"-?\d{1,3}(?:[ .]\d{3})*,\d{2}|-?\d+\.\d{2}"
# Linha típica: 05-10-2026 [05-10-2026] COMPRA NETFLIX.COM   9,99   1.234,56
_LINHA = re.compile(rf"^\s*({_DATA})\s+(?:{_DATA}\s+)?(.+?)\s+({_VALOR})(?:\s*€)?(?:\s+({_VALOR})(?:\s*€)?)?\s*$")
_SALDO_INICIAL = re.compile(rf"saldo\s+(?:inicial|anterior)[^\d-]*({_VALOR})", re.IGNORECASE)


def _ler_pdf_tabelas(pdf) -> pd.DataFrame | None:
    """1.ª tentativa: tabelas do PDF com colunas (mantém Débito/Crédito separados)."""
    linhas = []
    for pagina in pdf.pages:
        for tabela in pagina.extract_tables() or []:
            linhas.extend(tabela)
    if not linhas:
        return None
    bruto = pd.DataFrame(linhas)
    try:
        tabela = _tabela_com_cabecalho(bruto)
        # Cabeçalhos repetidos em cada página aparecem como linhas: retirá-los.
        primeira = str(tabela.columns[0])
        tabela = tabela[tabela.iloc[:, 0].astype(str) != primeira]
        resultado = normalizar_extrato(tabela)
        return resultado if len(resultado) else None
    except ValueError:
        return None


def _ler_pdf_texto(texto: str) -> pd.DataFrame:
    """2.ª tentativa: linha a linha. O sinal (+/-) vem da variação do saldo.

    Num PDF lido como texto perde-se em que coluna estava o valor (Débito ou Crédito),
    mas se cada linha tiver o saldo depois do movimento, basta ver se o saldo subiu
    ou desceu: saldo atual - saldo anterior = movimento com sinal.
    """
    m = _SALDO_INICIAL.search(texto)
    saldo_anterior = converter_numero(m.group(1)) if m else None
    movimentos = []
    for linha in texto.splitlines():
        r = _LINHA.match(linha)
        if not r:
            continue
        data, descricao, valor_txt, saldo_txt = r.groups()
        valor = converter_numero(valor_txt)
        saldo = converter_numero(saldo_txt) if saldo_txt else None
        if saldo is not None and saldo_anterior is not None:
            diferenca = round(saldo - saldo_anterior, 2)
            if abs(abs(diferenca) - abs(valor)) <= 0.01:
                valor = diferenca
            elif valor > 0:
                valor = -valor
        elif valor > 0 and not valor_txt.startswith("-"):
            valor = -valor  # sem saldo para confirmar: assumimos saída (o mais comum)
        if saldo is not None:
            saldo_anterior = saldo
        movimentos.append({"Data": data, "Descrição": descricao.strip(), "Montante": valor})
    if not movimentos:
        raise ValueError("Não encontrei movimentos neste PDF. Experimenta exportar em CSV ou Excel.")
    return normalizar_extrato(pd.DataFrame(movimentos))


def ler_extrato_pdf(conteudo: bytes) -> pd.DataFrame:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        por_tabelas = _ler_pdf_tabelas(pdf)
        if por_tabelas is not None:
            return por_tabelas
        texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
    return _ler_pdf_texto(texto)
