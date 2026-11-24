"""Leitura e análise de dados com cache (para não recalcular a cada clique).

O Streamlit volta a correr a página inteira a cada clique. Sem cache, cada clique no
"Corrigir" repetia a junção dos extratos e a deteção toda (até 250 ms com 3 extratos).
Com cache, as contas só se repetem quando mudam os ficheiros, as afinações ou o nome.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from contas.energia import carregar_ofertas
from contas.exemplo import extrato_csv_banco, gerar_extrato
from contas.extrato import carregar_extrato, diagnostico_tabela, juntar_extratos, ler_tabela
from contas.leitor_pdf import diagnostico_pdf
from contas.partilhas import detetar_partilhas
from contas.recorrentes import Parametros, detetar_recorrentes, possiveis_subscricoes, preparar


@st.cache_data(show_spinner=False)
def csv_exemplo() -> bytes:
    return extrato_csv_banco(gerar_extrato())


@st.cache_data(show_spinner=False)   # enquanto lê, a página mostra o talão a cinzento
def ler_extrato(conteudo: bytes, nome: str = "") -> pd.DataFrame:
    return carregar_extrato(conteudo, nome)


@st.cache_data(show_spinner=False, max_entries=16)
def juntar(lidos: list[pd.DataFrame]) -> pd.DataFrame:
    return juntar_extratos(lidos)


@st.cache_data(show_spinner=False, max_entries=32)
def analisar(extrato: pd.DataFrame, min_pagamentos: int = 3, regularidade: float = 0.7,
             variacao: float = 0.15, nome: str = "") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """A deteção toda: (recorrentes, "a confirmar", contas divididas)."""
    parametros = Parametros(min_pagamentos=min_pagamentos, regularidade_minima=regularidade,
                            variacao_maxima_valor=variacao)
    recorrentes = detetar_recorrentes(extrato, parametros, nome=nome)
    return (recorrentes, possiveis_subscricoes(extrato, recorrentes, nome=nome),
            detetar_partilhas(extrato, recorrentes, nome=nome, parametros=parametros))


@st.cache_data(show_spinner=False, max_entries=16)
def movimentos(extrato: pd.DataFrame, nome: str = "") -> pd.DataFrame:
    """As saídas com comerciante e categoria (para "Ver os movimentos de")."""
    return preparar(extrato, nome)


@st.cache_data(show_spinner=False)
def diagnostico(conteudo: bytes, nome: str) -> dict:
    """Estrutura anónima de um ficheiro (para reportar problemas sem dados pessoais)."""
    if nome.lower().endswith(".pdf") or conteudo[:4] == b"%PDF":
        return diagnostico_pdf(conteudo)
    try:
        tabela = ler_tabela(conteudo, nome)
        return {"metodo": "tabela", "texto": diagnostico_tabela(tabela), "erro": ""}
    except Exception as erro:  # noqa: BLE001
        return {"metodo": "-", "texto": "", "erro": str(erro)}


@st.cache_data(show_spinner=False)
def ofertas_base() -> pd.DataFrame:
    return carregar_ofertas()
