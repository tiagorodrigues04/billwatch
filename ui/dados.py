"""Leitura de dados com cache (para não recalcular a cada clique)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from contas.energia import carregar_ofertas
from contas.exemplo import extrato_csv_banco, gerar_extrato
from contas.extrato import carregar_extrato, diagnostico_tabela, ler_tabela
from contas.leitor_pdf import diagnostico_pdf


@st.cache_data(show_spinner=False)
def csv_exemplo() -> bytes:
    return extrato_csv_banco(gerar_extrato())


@st.cache_data(show_spinner="A ler o extrato…")
def ler_extrato(conteudo: bytes, nome: str = "") -> pd.DataFrame:
    return carregar_extrato(conteudo, nome)


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
