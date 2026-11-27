"""Supermercado: quanto se gasta, em que cadeias e com que frequência.

O extrato diz onde se comprou e quanto, mas não o quê. Por isso aqui está só o que dá para
saber com ele: o gasto por mês e por cadeia, quantas idas, o valor médio de cada ida e quanto
pesam as idas pequenas.

Para "mudar de cadeia compensa?" usa-se o índice de preços anual da DECO PROteste para os
supermercados online (dados/precos_supermercados.csv; 100 = o mais barato do ano). É a média
de um cabaz de mais de 200 produtos, com preços online e sem promoções nem descontos de cartão:
dá uma ordem de grandeza, não o preço do carrinho de cada pessoa.

O El Corte Inglés fica de fora das compras: no extrato não dá para separar o supermercado do
resto da loja.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .texto import sem_acentos

PASTA_DADOS = Path(__file__).resolve().parent.parent / "dados"
DIAS_POR_MES = 30.4               # o mesmo mês que na deteção das contas fixas
LIMITE_IDA_PEQUENA = 10.0         # € — uma compra abaixo disto é uma "ida pequena"
DIAS_MES_COMPLETO = 25            # um mês entra no gráfico se o extrato cobrir pelo menos estes dias

# Cadeia -> padrão na descrição (em maiúsculas e sem acentos). Ganha o primeiro que encaixar.
CADEIAS: dict[str, str] = {
    "Continente": r"\bCONTINENTE\b",
    "Pingo Doce": r"\bPINGO ?DOCE\b",
    "Lidl": r"\bLIDL\b",
    "Mercadona": r"\bMERCADONA\b",
    "Aldi": r"\bALDI\b",
    "Auchan": r"\bAUCHAN\b|\bJUMBO\b",
    "Intermarché": r"\bINTERMARCHE\b",
    "Minipreço": r"\bMINI ?PRECO\b",
    "Froiz": r"\bFROIZ\b",
    "Apolónia": r"\bAPOLONIA\b",
    "360Hyper": r"\b360 ?HYPER\b",
    "Spar": r"\bSPAR\b",
    "Coviran": r"\bCOVIRAN\b",
    "Meu Super": r"\bMEU SUPER\b",
    "Amanhecer": r"\bAMANHECER\b",
}
_PADROES = [(nome, re.compile(padrao)) for nome, padrao in CADEIAS.items()]
# As bombas de gasolina destas cadeias aparecem com o mesmo nome, mas não são compras de supermercado.
_COMBUSTIVEL = re.compile(r"COMBUST|GASOLIN|GASOLEO|POSTO D|ABASTEC|\bBOMBAS?\b")
# Só uma entrada com uma destas palavras é uma devolução; um ordenado do Pingo Doce não desconta nada.
_DEVOLUCAO = re.compile(r"DEVOL|ESTORN|REEMBOLS|ANULA")

COLUNAS_COMPRAS = ["data", "cadeia", "descricao", "montante"]


def _normalizar(descricao) -> str:
    return sem_acentos(str(descricao)).upper()


def cadeia(descricao: str) -> str | None:
    """A cadeia de supermercados de um movimento, ou None se não for de um supermercado."""
    texto = _normalizar(descricao)
    if _COMBUSTIVEL.search(texto):
        return None
    return next((nome for nome, padrao in _PADROES if padrao.search(texto)), None)


def compras(extrato: pd.DataFrame) -> pd.DataFrame:
    """As compras em supermercados e as devoluções: data, cadeia, descrição e montante.

    O montante é positivo numa compra e negativo numa devolução (que desconta no gasto).
    """
    if extrato.empty:
        return pd.DataFrame(columns=COLUNAS_COMPRAS)
    cadeias = extrato["descricao"].map(cadeia)
    devolucao = extrato["descricao"].map(lambda d: bool(_DEVOLUCAO.search(_normalizar(d))))
    escolhidas = cadeias.notna() & ((extrato["valor"] < 0) | ((extrato["valor"] > 0) & devolucao))
    tabela = pd.DataFrame({"data": extrato.loc[escolhidas, "data"], "cadeia": cadeias[escolhidas],
                           "descricao": extrato.loc[escolhidas, "descricao"],
                           "montante": -extrato.loc[escolhidas, "valor"]})
    return tabela.sort_values("data", kind="stable").reset_index(drop=True)


def meses_cobertos(extrato: pd.DataFrame) -> float:
    """Quantos meses o extrato cobre, do primeiro ao último movimento (pode ser uma fração)."""
    dias = (extrato["data"].max() - extrato["data"].min()).days + 1
    return dias / DIAS_POR_MES


@dataclass(frozen=True)
class Resumo:
    meses: float                  # meses cobertos pelo extrato
    gasto_mensal: float           # descontadas as devoluções
    idas_mensal: float
    valor_medio: float            # de cada ida
    pequenas_mensal: float        # idas abaixo do limite, por mês
    pequenas_gasto_mensal: float
    limite: float
    por_cadeia: pd.DataFrame      # cadeia, gasto_mensal, idas_mensal, valor_medio, parte (do maior para o menor)


def resumir(tabela: pd.DataFrame, meses: float, limite: float = LIMITE_IDA_PEQUENA) -> Resumo:
    """As médias por mês, no total e por cadeia. `tabela` vem de compras()."""
    meses = max(meses, 1 / DIAS_POR_MES)
    idas = tabela[tabela["montante"] > 0]
    pequenas = idas[idas["montante"] < limite]
    total = float(tabela["montante"].sum())

    por_cadeia = pd.DataFrame({
        "gasto": tabela.groupby("cadeia")["montante"].sum(),
        "comprado": idas.groupby("cadeia")["montante"].sum(),
        "idas": idas.groupby("cadeia")["montante"].size(),
    }).fillna(0).reset_index(names="cadeia")
    por_cadeia = pd.DataFrame({
        "cadeia": por_cadeia["cadeia"],
        "gasto_mensal": por_cadeia["gasto"] / meses,
        "idas_mensal": por_cadeia["idas"] / meses,
        "valor_medio": (por_cadeia["comprado"] / por_cadeia["idas"].where(por_cadeia["idas"] > 0)).fillna(0.0),
        "parte": por_cadeia["gasto"] / total if total else 0.0,
    }).sort_values("gasto_mensal", ascending=False, kind="stable").reset_index(drop=True)

    return Resumo(
        meses=meses,
        gasto_mensal=total / meses,
        idas_mensal=len(idas) / meses,
        valor_medio=float(idas["montante"].mean()) if len(idas) else 0.0,
        pequenas_mensal=len(pequenas) / meses,
        pequenas_gasto_mensal=float(pequenas["montante"].sum()) / meses,
        limite=limite,
        por_cadeia=por_cadeia,
    )


def por_mes(tabela: pd.DataFrame, extrato: pd.DataFrame) -> pd.DataFrame:
    """O gasto de cada mês que o extrato cobre (quase) todo: os meses cortados no início e no fim ficam de fora."""
    inicio, fim = extrato["data"].min().normalize(), extrato["data"].max().normalize()
    meses_da_compra = tabela["data"].dt.to_period("M")
    linhas = []
    for mes in pd.period_range(inicio, fim, freq="M"):
        coberto = (min(mes.end_time.normalize(), fim) - max(mes.start_time, inicio)).days + 1
        if coberto >= min(DIAS_MES_COMPLETO, mes.days_in_month):
            gasto = float(tabela.loc[meses_da_compra == mes, "montante"].sum())
            linhas.append({"mes": mes.to_timestamp(), "gasto": gasto})
    return pd.DataFrame(linhas, columns=["mes", "gasto"])


def indices_de_precos(caminho: Path | None = None) -> pd.DataFrame:
    """O índice de preços dos supermercados online: cadeia, indice (100 = o mais barato), ano, fonte, url."""
    return pd.read_csv(caminho or PASTA_DADOS / "precos_supermercados.csv")


def mais_barata(indices: pd.DataFrame) -> str:
    return str(indices.loc[indices["indice"].idxmin(), "cadeia"])


def mudar_de_cadeia(por_cadeia: pd.DataFrame, indices: pd.DataFrame) -> pd.DataFrame:
    """Quanto se poupava por mês em cada cadeia, se o mesmo carrinho custasse o que custa na mais barata do índice.

    poupança = gasto × (1 − índice da mais barata ÷ índice da cadeia). Uma cadeia que não está no
    índice (o Lidl, o Aldi e o Mercadona não entram no estudo) fica sem índice e sem poupança.
    """
    referencia = float(indices["indice"].min())
    tabela = por_cadeia[["cadeia", "gasto_mensal"]].merge(indices[["cadeia", "indice"]], on="cadeia", how="left")
    # Uma cadeia só com devoluções tem gasto negativo: não há nada a poupar lá.
    tabela["poupanca_mensal"] = (tabela["gasto_mensal"] * (1 - referencia / tabela["indice"])).clip(lower=0)
    return tabela
