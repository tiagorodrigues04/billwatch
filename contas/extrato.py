"""Leitura e limpeza de extratos bancários (CSV, Excel, HTML-xls; o PDF está em leitor_pdf.py).

Cada banco exporta à sua maneira: separador ';' ou ',', "1.234,56" ou "1,234.56",
uma coluna "Montante" com sinal, duas colunas "Débito"/"Crédito", ou um valor positivo
com uma coluna "D/C" ao lado; linhas de título antes da tabela; vários blocos
(ex.: Revolut: resumo + conta + cripto); datas em "dd-mm-aaaa", "aaaa-mm-dd" ou
datas reais do Excel.

Tudo isto acaba numa tabela padrão com três colunas:
    data (datetime) · descricao (texto) · valor (float, negativo = saída)

Se as colunas não forem reconhecidas, é lançado FormatoDesconhecido com a tabela
lida, para a app pedir ao utilizador que diga qual é qual (normalizar_com_mapa).
"""

from __future__ import annotations

import csv
import io
import re

import pandas as pd

from .texto import (anonimizar, chave, converter_datas, converter_numero, corrigir_texto_pdf,
                    sem_acentos)

__all__ = [
    "FormatoDesconhecido", "carregar_extrato", "ler_tabela", "detetar_colunas", "normalizar_extrato",
    "normalizar_com_mapa", "sugerir_mapa", "juntar_extratos", "chave_comerciante", "e_debito_direto",
    "converter_numero", "corrigir_texto_pdf", "anonimizar", "diagnostico_tabela",
]


class FormatoDesconhecido(ValueError):
    """O ficheiro foi lido, mas não percebemos que coluna é qual."""

    def __init__(self, mensagem: str, tabela: pd.DataFrame | None = None):
        super().__init__(mensagem)
        self.tabela = tabela


# Palavras que costumam aparecer no nome de cada coluna, em PT e EN (por ordem de prioridade).
NOMES_DATA = ["data mov", "data lanc", "data oper", "data transa", "started", "data de inicio",
              "data", "date", "dia"]
NOMES_DESCRICAO = ["descri", "designa", "movimento", "historico", "detalhe", "concept", "narrativ",
                   "merchant", "beneficiario", "referencia", "observa", "texto", "details", "nome", "name"]
NOMES_VALOR = ["montante", "valor", "amount", "importancia", "quantia"]
NOMES_DEBITO = ["debito", "debit", "saida", "retirado", "money out", "paid out", "enviado", "withdraw"]
NOMES_CREDITO = ["credito", "credit", "entrada", "recebido", "money in", "paid in", "deposit"]
NOMES_MOEDA = ["moeda", "currency", "divisa"]
NOMES_ESTADO = ["state", "estado", "status"]
_NAO_E_VALOR = ("data", "date", "saldo", "balance", "dispon", "contabil", "fee", "comiss", "taxa")

_MARCAS_DEBITO = {"d", "db", "deb", "debito", "debit", "dr", "-", "saida", "s"}
_MARCAS_CREDITO = {"c", "cr", "cred", "credito", "credit", "+", "entrada", "e"}
_LINHAS_SALDO = re.compile(r"saldo\s+(?:inicial|anterior|final|de abertura|transportado)|opening balance|"
                           r"closing balance|balance brought|a transportar", re.IGNORECASE)


# ---------------------------------------------------------------------------
# 1. Ficheiro -> linhas (listas de células)
# ---------------------------------------------------------------------------

def _decodificar(conteudo: bytes) -> str:
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1")


def _pontuacao_separador(texto: str, separador: str) -> int:
    """Quantas linhas têm 3+ células e o número de células mais comum."""
    linhas = [l for l in csv.reader(io.StringIO(texto[:20000]), delimiter=separador) if any(c.strip() for c in l)]
    contagens = [len(l) for l in linhas if len(l) >= 3]
    if not contagens:
        return 0
    moda = max(set(contagens), key=contagens.count)
    return contagens.count(moda) * (1 + moda / 100)


def _linhas_csv(conteudo: bytes) -> list[list]:
    texto = _decodificar(conteudo)
    separador = max([";", ",", "\t", "|"], key=lambda s: _pontuacao_separador(texto, s))
    return list(csv.reader(io.StringIO(texto), delimiter=separador))


def _linhas_html(conteudo: bytes) -> list[list]:
    """Alguns bancos dão um '.xls' que na verdade é uma página HTML com uma tabela."""
    tabelas = pd.read_html(io.StringIO(_decodificar(conteudo)), thousands=None, decimal=",")
    linhas: list[list] = []
    for tabela in tabelas:
        # O pandas pode ter usado uma linha como cabeçalho; voltamos a pô-la como dados.
        cabecalho = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in tabela.columns]
        linhas += [cabecalho] + tabela.values.tolist() + [[]]
    return linhas


def _linhas_excel(conteudo: bytes) -> list[list]:
    # "calamine" lê .xlsx e .xls antigos e é o motor recomendado pelo pandas; os outros
    # ficam de reserva (o xlrd vai deixar de ser suportado em versões futuras do pandas).
    motores = ["calamine", "openpyxl" if conteudo[:2] == b"PK" else "xlrd"]
    folhas, erro = None, None
    for motor in motores:
        try:
            folhas = pd.read_excel(io.BytesIO(conteudo), header=None, sheet_name=None, engine=motor)
            break
        except ImportError as e:
            erro = e
    if folhas is None:
        raise erro
    linhas: list[list] = []
    for folha in folhas.values():
        linhas += folha.values.tolist() + [[]]
    return linhas


# ---------------------------------------------------------------------------
# 2. Linhas -> tabela (encontrar o cabeçalho e os blocos de movimentos)
# ---------------------------------------------------------------------------

def _vazio(celula) -> bool:
    return celula is None or (isinstance(celula, float) and pd.isna(celula)) or str(celula).strip() in ("", "nan")


def _contem(texto: str, nomes: list[str]) -> bool:
    return any(n in texto for n in nomes)


def e_linha_cabecalho(celulas) -> bool:
    """Uma linha é cabeçalho de movimentos se tiver 3+ células curtas, uma de data e uma de valor."""
    preenchidas = [chave(str(c)) for c in celulas if not _vazio(c)]
    if len(preenchidas) < 3 or any(len(c) > 40 for c in preenchidas):
        return False
    tem_data = any(_contem(c, NOMES_DATA) for c in preenchidas)
    tem_valor = any(_contem(c, NOMES_VALOR + NOMES_DEBITO + NOMES_CREDITO) and not c.startswith("data")
                    for c in preenchidas)
    return tem_data and tem_valor


def _nomes_unicos(celulas: list) -> list[str]:
    nomes, vistos = [], {}
    for i, c in enumerate(celulas):
        nome = str(c).strip() if not _vazio(c) else f"Coluna {i + 1}"
        if nome in vistos:
            vistos[nome] += 1
            nome = f"{nome} ({vistos[nome]})"
        else:
            vistos[nome] = 1
        nomes.append(nome)
    return nomes


def _tabela(cabecalho: list, corpo: list[list]) -> pd.DataFrame:
    largura = max([len(cabecalho)] + [len(l) for l in corpo])
    cabecalho = list(cabecalho) + [None] * (largura - len(cabecalho))
    corpo = [list(l) + [None] * (largura - len(l)) for l in corpo]
    df = pd.DataFrame(corpo, columns=_nomes_unicos(cabecalho))
    # Colunas sem nome e sem dados (lixo de formatação) saem.
    vazias = [c for c in df.columns if c.startswith("Coluna ") and df[c].map(_vazio).all()]
    return df.drop(columns=vazias)


def tabela_de_linhas(linhas: list[list]) -> pd.DataFrame:
    """Encontra os cabeçalhos de movimentos e junta os blocos com as mesmas colunas.

    Alguns bancos põem linhas soltas antes da tabela (nome, IBAN...). A Revolut vai mais
    longe: um bloco de resumo e depois um bloco de movimentos por conta/produto, cada um
    com o seu cabeçalho. Em PDFs, o cabeçalho repete-se em cada página. Lemos o que vem
    depois de cada cabeçalho até ao próximo e juntamos os blocos com as mesmas colunas;
    o tipo de bloco com mais linhas ganha (o resumo, se existir, fica de fora).
    Linhas que não são movimentos (títulos, totais, rodapés) caem mais tarde por não
    terem data ou valor.
    """
    cabecalhos = [i for i, l in enumerate(linhas) if e_linha_cabecalho(l)]
    if not cabecalhos:
        for i, l in enumerate(linhas):
            if sum(not _vazio(c) for c in l) >= 3:
                return _tabela(l, [x for x in linhas[i + 1:] if any(not _vazio(c) for c in x)])
        raise ValueError("O ficheiro parece estar vazio.")
    grupos: dict[tuple, list] = {}
    for n, inicio in enumerate(cabecalhos):
        fim = cabecalhos[n + 1] if n + 1 < len(cabecalhos) else len(linhas)
        corpo = [l for l in linhas[inicio + 1:fim] if any(not _vazio(c) for c in l)]
        chave_cab = tuple(chave(str(c)) for c in linhas[inicio] if not _vazio(c))
        grupos.setdefault(chave_cab, []).append((linhas[inicio], corpo))
    melhor = max(grupos.values(), key=lambda blocos: sum(len(c) for _, c in blocos))
    return pd.concat([_tabela(cab, corpo) for cab, corpo in melhor], ignore_index=True)


def ler_tabela(conteudo: bytes, nome: str = "") -> pd.DataFrame:
    """Lê um CSV/Excel/HTML-xls e devolve a tabela de movimentos em bruto (ainda por interpretar)."""
    nome = nome.lower()
    inicio = conteudo[:300].lstrip().lower()
    if inicio.startswith(b"<"):
        linhas = _linhas_html(conteudo)
    elif conteudo[:2] == b"PK" or conteudo[:4] == b"\xd0\xcf\x11\xe0" or nome.endswith((".xlsx", ".xls")):
        linhas = _linhas_excel(conteudo)
    else:
        linhas = _linhas_csv(conteudo)
    return tabela_de_linhas(linhas)


# ---------------------------------------------------------------------------
# 3. Tabela -> que coluna é qual
# ---------------------------------------------------------------------------

def _encontrar(colunas: list[str], candidatos: list[str], excluir=frozenset()) -> str | None:
    """Primeira coluna cujo nome contém um dos candidatos (por ordem de prioridade)."""
    for candidato in candidatos:
        for coluna in colunas:
            if coluna not in excluir and candidato in chave(coluna):
                return coluna
    return None


def _marca_sinal(valor) -> float | None:
    if _vazio(valor):
        return None
    c = chave(str(valor)).strip(".")
    if c in _MARCAS_DEBITO:
        return -1.0
    if c in _MARCAS_CREDITO:
        return 1.0
    return None


def _taxa(serie: pd.Series, funcao) -> float:
    preenchidos = serie[~serie.map(_vazio)]
    if preenchidos.empty:
        return 0.0
    return float(preenchidos.map(lambda v: funcao(v) is not None).mean())


def detetar_colunas(df: pd.DataFrame) -> dict:
    """Descobre que coluna é a data, a descrição, o valor (ou débito/crédito), etc.

    Lança FormatoDesconhecido (com a tabela) se faltar alguma coluna essencial.
    """
    mapa = sugerir_mapa(df)
    em_falta = [k for k in ("data", "descricao") if mapa[k] is None]
    if not (mapa["valor"] or mapa["debito"] or mapa["credito"]):
        em_falta.append("valor")
    if em_falta:
        raise FormatoDesconhecido(f"Não reconheci a(s) coluna(s): {', '.join(em_falta)}.", df)
    return mapa


def sugerir_mapa(df: pd.DataFrame) -> dict:
    """O melhor palpite para cada coluna (pode deixar algumas a None)."""
    colunas = [str(c) for c in df.columns]
    nao_valor = {c for c in colunas if any(n in chave(c) for n in _NAO_E_VALOR)}
    mapa: dict = {"data": _encontrar(colunas, NOMES_DATA)}
    usadas = {mapa["data"]}
    mapa["descricao"] = _encontrar(colunas, NOMES_DESCRICAO, excluir=nao_valor | usadas)
    usadas |= {mapa["descricao"]}
    mapa["valor"] = _encontrar(colunas, NOMES_VALOR, excluir=nao_valor | usadas)
    mapa["debito"] = _encontrar(colunas, NOMES_DEBITO, excluir=nao_valor | usadas | {mapa["valor"]})
    mapa["credito"] = _encontrar(colunas, NOMES_CREDITO, excluir=nao_valor | usadas | {mapa["valor"]})
    mapa["moeda"] = _encontrar(colunas, NOMES_MOEDA)
    mapa["estado"] = _encontrar(colunas, NOMES_ESTADO)
    usadas |= {mapa[k] for k in ("valor", "debito", "credito", "moeda", "estado")}

    # Sem nome reconhecível para a data: a coluna com mais datas válidas.
    if mapa["data"] is None:
        candidatas = [(c, _taxa(df[c], lambda v: v if not pd.isna(converter_datas(pd.Series([v]))[0]) else None))
                      for c in colunas if c not in usadas]
        candidatas = [x for x in candidatas if x[1] >= 0.7]
        mapa["data"] = max(candidatas, key=lambda x: x[1])[0] if candidatas else None
        usadas |= {mapa["data"]}

    # Sem nome para a descrição: a coluna de texto mais comprida.
    if mapa["descricao"] is None:
        texto = [c for c in colunas if c not in usadas | nao_valor and _taxa(df[c], converter_numero) < 0.5]
        if texto:
            mapa["descricao"] = max(texto, key=lambda c: df[c].astype(str).str.len().mean())
            usadas |= {mapa["descricao"]}

    # Valor positivo com uma coluna "D/C" (ou "Tipo: Débito/Crédito") ao lado.
    mapa["sinal"] = None
    if mapa["valor"] is not None:
        for c in colunas:
            if c not in usadas and _taxa(df[c], _marca_sinal) >= 0.8:
                mapa["sinal"] = c
                break

    return mapa


# ---------------------------------------------------------------------------
# 4. Tabela + mapa -> extrato padrão
# ---------------------------------------------------------------------------

def normalizar_com_mapa(df: pd.DataFrame, mapa: dict, inverter: bool = False) -> pd.DataFrame:
    """Aplica um mapa de colunas (automático ou escolhido pelo utilizador)."""
    df = df.reset_index(drop=True)
    numero = lambda col: df[col].map(converter_numero).astype(float)  # noqa: E731
    if mapa.get("valor"):
        valores = numero(mapa["valor"])
        if mapa.get("sinal"):
            marcas = df[mapa["sinal"]].map(_marca_sinal)
            valores = valores.where(marcas.isna(), valores.abs() * marcas)
    else:
        debitos = numero(mapa["debito"]).abs() if mapa.get("debito") else pd.Series(float("nan"), index=df.index)
        creditos = numero(mapa["credito"]).abs() if mapa.get("credito") else pd.Series(float("nan"), index=df.index)
        valores = creditos.fillna(0) - debitos.fillna(0)
        valores[debitos.isna() & creditos.isna()] = float("nan")
    if inverter:
        valores = -valores

    resultado = pd.DataFrame({
        "data": converter_datas(df[mapa["data"]]),
        "descricao": df[mapa["descricao"]].map(lambda v: "" if _vazio(v) else corrigir_texto_pdf(str(v)).strip()),
        "valor": valores,
    })
    manter = pd.Series(True, index=df.index)
    # Movimentos revertidos, recusados ou falhados não aconteceram (ex.: Revolut).
    if mapa.get("estado"):
        estado = df[mapa["estado"]].astype(str).map(chave)
        manter &= ~estado.str.contains("revert|declin|fail|cancel|recusad|falhad|anulad|rejeit", regex=True)
    # Contas multimoeda (ex.: cripto na Revolut): só a moeda principal (EUR, se existir).
    if mapa.get("moeda"):
        moeda = df[mapa["moeda"]].astype(str).str.strip().str.upper()
        validas = moeda[~df[mapa["moeda"]].map(_vazio)]
        if not validas.empty:
            principal = "EUR" if (validas == "EUR").any() else validas.mode()[0]
            manter &= (moeda == principal) | df[mapa["moeda"]].map(_vazio)
    # Linhas de saldo inicial/final não são movimentos.
    manter &= ~resultado["descricao"].str.contains(_LINHAS_SALDO)
    resultado = resultado[manter.values].dropna(subset=["data", "valor"])
    resultado = resultado[resultado["valor"].abs() > 0.004]
    return resultado.sort_values("data", kind="stable").reset_index(drop=True)


def normalizar_extrato(df: pd.DataFrame) -> pd.DataFrame:
    """Converte uma tabela de extrato qualquer no formato padrão (data, descricao, valor)."""
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    mapa = detetar_colunas(df)
    resultado = normalizar_com_mapa(df, mapa)
    if resultado.empty:
        raise FormatoDesconhecido("Encontrei as colunas, mas nenhuma linha com data e valor válidos.", df)
    return resultado


def carregar_extrato(conteudo: bytes, nome: str = "") -> pd.DataFrame:
    """Ponto de entrada: bytes do ficheiro (CSV, Excel, HTML-xls ou PDF) -> extrato padrão."""
    if not conteudo or not conteudo.strip():
        raise ValueError("O ficheiro está vazio.")
    if nome.lower().endswith(".pdf") or conteudo[:4] == b"%PDF":
        from .leitor_pdf import ler_extrato_pdf
        return ler_extrato_pdf(conteudo)
    try:
        tabela = ler_tabela(conteudo, nome)
    except ValueError:
        raise
    except Exception as erro:  # Excel danificado, HTML sem tabelas, binário qualquer...
        raise ValueError("Não consegui ler este ficheiro. Confirma que é um extrato em CSV, Excel ou PDF "
                         "exportado do banco.") from erro
    return normalizar_extrato(tabela)


def diagnostico_tabela(df: pd.DataFrame, linhas: int = 12) -> str:
    """Primeiras linhas da tabela em bruto, anonimizadas (para reportar problemas)."""
    cabecalho = " | ".join(str(c) for c in df.columns)
    corpo = [" | ".join(anonimizar("" if _vazio(v) else str(v)) for v in l) for l in df.head(linhas).values]
    return "\n".join([cabecalho] + corpo)


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
        df["_dia"] = df["data"].dt.normalize()
        df["_ocorrencia"] = df.groupby(["_dia", "descricao", "valor"]).cumcount()
        partes.append(df)
    junto = pd.concat(partes, ignore_index=True)
    junto = junto.drop_duplicates(subset=["_dia", "descricao", "valor", "_ocorrencia"])
    return junto.drop(columns=["_dia", "_ocorrencia"]).sort_values("data", kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Nome do comerciante
# ---------------------------------------------------------------------------

# Prefixos que os bancos acrescentam à descrição e que não identificam o comerciante.
_RUIDO = re.compile(
    r"\b(COMPRA|COMPRAS|PAG(AMENTO)?|PAGTO|DD|DEB(ITO)?|DIRECTO|DIRETO|TRF|TRANSF(ERENCIA)?|"
    r"MB ?WAY|MBWAY|MB|CARTAO|CARTOO|CART|CARD|CONTACTLESS|ONLINE|WWW|COM|PT|LDA|SA|S A|REF|N|NO|ENT|"
    r"COBRANCA|COBRAN|SDD|ADC|CID|IMEDIATA|SEPA|DE|DA|DO|PARA|UNIPESSOAL|PAYMENT|TO|FROM|"
    r"PORTUGAL|LISBOA|PORTO|COIMBRA|EUR|VISA|MASTERCARD|APPLE PAY|GOOGLE PAY)\b"
)
_DEBITO_DIRETO = re.compile(r"\b(SDD|DD|DEB\.? ?DIRE?C?TO|DEBITO DIRE?C?TO|COBRANCA|DIRECT DEBIT)\b")
SEPARADOR_DETALHE = " · "   # o leitor de PDF junta aqui a 2.ª linha da descrição


def e_debito_direto(descricao: str) -> bool:
    return bool(_DEBITO_DIRETO.search(sem_acentos(corrigir_texto_pdf(descricao)).upper()))


def _tokens(texto: str) -> list[str]:
    texto = sem_acentos(corrigir_texto_pdf(texto)).upper()
    texto = re.sub(r"[^A-Z0-9 ]", " ", texto)       # pontuação fora
    texto = re.sub(r"\b\w*\d\w*\b", " ", texto)       # tokens com números (refs, datas, cartões)
    texto = _RUIDO.sub(" ", texto)
    return [t for t in texto.split() if len(t) > 1]


def chave_comerciante(descricao: str) -> str:
    """Reduz uma descrição bancária a uma chave estável.

    "COMPRA 4521 NETFLIX.COM 866-579 12/03"           -> "NETFLIX"
    "DD EDP COMERCIAL REF 123456789"                  -> "EDP COMERCIAL"
    "Pagamento com cartão · Netflix.com" (PDF 2 linhas) -> "NETFLIX"
    """
    principal, _, detalhe = str(descricao).partition(SEPARADOR_DETALHE)
    tokens = _tokens(principal) or _tokens(detalhe)
    return " ".join(tokens[:2]) if tokens else sem_acentos(str(descricao)).upper().strip()
