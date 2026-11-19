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


def carregar_extrato(conteudo: bytes) -> pd.DataFrame:
    """Ponto de entrada: recebe os bytes do CSV e devolve o extrato normalizado."""
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
