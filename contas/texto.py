"""Funções base para ler números, datas e texto de extratos bancários.

Tudo o que é "como é que este banco escreve um número/uma data" vive aqui,
para os leitores de CSV, Excel e PDF usarem exatamente as mesmas regras.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

import pandas as pd


def sem_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c))


def decodificar(conteudo: bytes) -> str:
    """Bytes de um ficheiro de texto -> texto: UTF-8 (com ou sem BOM) ou cp1252 (o Excel em português)."""
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1")


def chave(texto: str) -> str:
    """Texto em minúsculas e sem acentos, para comparar nomes de colunas."""
    return sem_acentos(texto).lower().strip()


def corrigir_texto_pdf(texto: str) -> str:
    """Corrige artefactos comuns da extração de PDFs.

    Alguns PDFs (ex.: Novo Banco) têm letras que o pdfplumber não sabe mapear e que
    aparecem como "(cid:231)". O número é o código da letra: 231 = "ç".
    """
    def trocar(m: re.Match) -> str:
        codigo = int(m.group(1))
        return chr(codigo) if 32 <= codigo < 256 else ""
    texto = re.sub(r"\(cid:(\d+)\)", trocar, str(texto))
    return texto.replace("Cartºo", "Cartão").replace("CARTºO", "CARTÃO")


# ---------------------------------------------------------------------------
# Números
# ---------------------------------------------------------------------------

_ESPACOS = (" ", " ", " ", " ")
_MARCAS_DEBITO = {"D", "DB", "DEB", "DR", "DEBITO", "DEBIT"}
_MARCAS_CREDITO = {"C", "CR", "CRED", "CREDITO", "CREDIT"}


def converter_numero(valor) -> float | None:
    """Converte um valor monetário escrito de qualquer forma num float.

    Aceita: "1.234,56"  "1,234.56"  "-12,99"  "+12,99"  "12,99-"  "(12,99)"
            "€ 7,99"  "7,99 €"  "-€7.99"  "7,99 EUR"  "1 234,56"  "9,99 D"  "9,99 C"  7.99
    "D"/"DB" no fim = débito (negativo); "C"/"CR" = crédito (positivo).
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().upper()
    for e in _ESPACOS:
        texto = texto.replace(e, "")
    texto = texto.replace("€", "").replace("EUR", "")
    if not texto:
        return None

    sinal = 1.0
    m = re.match(r"^(.*?\d)([A-Z]+)$", texto)            # 9,99D / 9,99CR
    if m and (m.group(2) in _MARCAS_DEBITO or m.group(2) in _MARCAS_CREDITO):
        texto = m.group(1)
        sinal = -1.0 if m.group(2) in _MARCAS_DEBITO else 1.0
    if texto.startswith("(") and texto.endswith(")"):
        sinal, texto = -1.0, texto[1:-1]
    if texto.endswith("-"):                                # 12,99-
        sinal, texto = -1.0, texto[:-1]
    if texto.startswith("-"):
        sinal, texto = -1.0, texto[1:]
    elif texto.startswith("+"):
        texto = texto[1:]
    if not re.fullmatch(r"[\d.,]+", texto) or not re.search(r"\d", texto):
        return None

    if "," in texto and "." in texto:
        # O separador que aparece por último é o decimal.
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        # Uma vírgula = decimal ("12,99", "0,1580"); várias = milhares em inglês ("1,234,567").
        texto = texto.replace(",", "") if texto.count(",") > 1 else texto.replace(",", ".")
    elif texto.count(".") > 1 or re.fullmatch(r"[1-9]\d{0,2}\.\d{3}", texto):
        texto = texto.replace(".", "")                     # "1.234" ou "1.234.567" = milhares
    try:
        return sinal * float(texto)
    except ValueError:
        return None


# Um valor monetário dentro de texto (PDF): exige 2 casas decimais para não apanhar
# números de referência, quantidades ou anos.
VALOR_RE = re.compile(
    r"^(?:[-+]|\()?\s?(?:€|EUR)?\s?"
    r"(?:\d{1,3}(?:[.   ]\d{3})+,\d{2}|\d{1,3}(?:,\d{3})+\.\d{2}|\d+[,.]\d{2})"
    r"\)?-?\s?(?:€|EUR)?$",
    re.IGNORECASE,
)


def e_valor(texto: str) -> bool:
    return bool(VALOR_RE.match(texto.strip()))


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------

MESES = {
    "jan": 1, "janeiro": 1, "january": 1,
    "fev": 2, "fevereiro": 2, "feb": 2, "february": 2,
    "mar": 3, "marco": 3, "march": 3,
    "abr": 4, "abril": 4, "apr": 4, "april": 4,
    "mai": 5, "maio": 5, "may": 5,
    "jun": 6, "junho": 6, "june": 6,
    "jul": 7, "julho": 7, "july": 7,
    "ago": 8, "agosto": 8, "aug": 8, "august": 8,
    "set": 9, "setembro": 9, "sep": 9, "sept": 9, "september": 9,
    "out": 10, "outubro": 10, "oct": 10, "october": 10,
    "nov": 11, "novembro": 11, "november": 11,
    "dez": 12, "dezembro": 12, "dec": 12, "december": 12,
}
_MES = r"([a-z]{3,9})\.?"
_PADROES_DATA = [
    # (regex, ordem dos grupos)
    (re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?![\d])"), "ymd"),
    (re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?![\d])"), "dmy"),
    (re.compile(rf"(\d{{1,2}})(?:\s+de)?\s+{_MES}(?:\s+de)?,?\s+(\d{{4}})(?![\d])"), "dMy"),
    (re.compile(rf"{_MES}\s+(\d{{1,2}}),?\s+(\d{{4}})(?![\d])"), "Mdy"),
    (re.compile(r"(\d{1,2})[-/.](\d{1,2})(?![-/.\d])"), "dm"),
    (re.compile(rf"(\d{{1,2}})(?:\s+de)?\s+{_MES}(?![a-z])"), "dM"),
]


def _montar_data(ano: int | None, mes: int, dia: int) -> date | None:
    if ano is not None and ano < 100:
        ano += 2000
    if ano is not None and not 1990 <= ano <= 2100:
        return None
    if not (1 <= mes <= 12 and 1 <= dia <= 31):
        return None
    try:
        return date(ano if ano is not None else 2000, mes, dia)
    except ValueError:
        return None


def ler_data_inicio(texto: str) -> tuple[date, int, bool] | None:
    """Procura uma data no INÍCIO do texto.

    Devolve (data, nº de caracteres usados, tem_ano) ou None.
    Formatos: 2026-10-05 · 05-10-2026 · 05/10/26 · 05.10.2026 · 5 out 2026 ·
    5 de out. de 2026 · Oct 5, 2026 · 05.10 (sem ano) · 05 OUT (sem ano)
    """
    t = sem_acentos(texto).lower()
    inicio = len(t) - len(t.lstrip())
    t = t.lstrip()
    for padrao, ordem in _PADROES_DATA:
        m = padrao.match(t)
        if not m:
            continue
        g = m.groups()
        try:
            if ordem == "ymd":
                d = _montar_data(int(g[0]), int(g[1]), int(g[2]))
            elif ordem == "dmy":
                d = _montar_data(int(g[2]), int(g[1]), int(g[0]))
            elif ordem == "dMy":
                d = _montar_data(int(g[2]), MESES.get(g[1], 0), int(g[0]))
            elif ordem == "Mdy":
                d = _montar_data(int(g[2]), MESES.get(g[0], 0), int(g[1]))
            elif ordem == "dm":
                d = _montar_data(None, int(g[1]), int(g[0]))
            else:  # dM
                d = _montar_data(None, MESES.get(g[1], 0), int(g[0]))
        except ValueError:
            d = None
        if d is not None:
            return d, inicio + m.end(), ordem not in ("dm", "dM")
    return None


def converter_datas(serie: pd.Series) -> pd.Series:
    """Converte uma coluna de datas escrita de qualquer forma.

    - datas reais do Excel ficam como estão
    - números entre 20000 e 80000 são datas "série" do Excel (dias desde 1899-12-30)
    - "aaaa-mm-dd" (ISO, Revolut) e "dd-mm-aaaa" (bancos PT) — não dá para usar
      dayfirst=True em tudo: "2026-10-05" passaria a 10 de maio
    - o que o pandas não perceber ("5 out 2026", "Oct 5, 2026") vai para ler_data_inicio
    """
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie
    numeros = pd.to_numeric(serie, errors="coerce")
    if numeros.notna().mean() > 0.8 and numeros.dropna().between(20000, 80000).all():
        return pd.to_datetime(numeros, unit="D", origin="1899-12-30", errors="coerce")

    texto = serie.astype(str).str.strip()
    comeca_pelo_ano = texto.str.match(r"^\d{4}[-/.]").mean() > 0.5
    resultado = pd.to_datetime(texto, dayfirst=not comeca_pelo_ano, yearfirst=comeca_pelo_ano,
                               errors="coerce", format="mixed")
    em_falta = resultado.isna() & texto.ne("") & texto.ne("nan") & texto.ne("None")
    for i in resultado.index[em_falta]:
        lido = ler_data_inicio(texto[i])
        if lido and lido[2]:
            resultado[i] = pd.Timestamp(lido[0])
    return resultado


# ---------------------------------------------------------------------------
# Anonimização (para o diagnóstico)
# ---------------------------------------------------------------------------

_PALAVRAS_SEGURAS = {
    "data", "datas", "date", "mov", "movimento", "movimentos", "valor", "valores", "descricao",
    "descritivo", "description", "debito", "debitos", "debit", "credito", "creditos", "credit",
    "saldo", "saldos", "balance", "montante", "amount", "disponivel", "contabilistico", "inicial",
    "anterior", "final", "eur", "euro", "euros", "total", "totais", "lancamento", "operacao", "tipo",
    "moeda", "currency", "extrato", "conta", "pagina", "page", "de", "a", "e", "do", "da", "dinheiro",
    "retirado", "recebido", "money", "in", "out", "state", "estado", "type", "fee", "comissao",
}


def anonimizar(texto: str) -> str:
    """Troca letras por 'x' e números por '9', exceto palavras típicas de cabeçalho.

    "05-10-2026 COMPRA NETFLIX.COM 9,99 1.234,56" -> "99-99-9999 xxxxxx xxxxxxx.xxx 9,99 9.999,99"
    Mantém a estrutura (espaços, pontuação, posição das colunas), que é o que é preciso
    para corrigir o leitor, sem revelar nomes, descrições, datas ou valores.
    """
    def trocar(m: re.Match) -> str:
        palavra = m.group(0)
        if sem_acentos(palavra).lower() in _PALAVRAS_SEGURAS:
            return palavra
        return re.sub(r"\d", "9", re.sub(r"[^\W\d_]", "x", palavra))
    return re.sub(r"\w+", trocar, str(texto))
