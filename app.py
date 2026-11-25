"""BillWatch: descobre quanto pagas todos os meses e onde podes poupar.

Correr localmente:  streamlit run app.py

Estrutura:
    app.py         configuração, estilo e navegação (este ficheiro)
    paginas/       uma página por ficheiro: subscricoes, supermercado, luz, sobre
    ui/            peças visuais (talão, gráficos), leitura dos ficheiros e cache
    contas/        a lógica: ler extratos, detetar pagamentos, supermercado, luz (sem Streamlit)
"""

from __future__ import annotations

import streamlit as st

from ui.componentes import rodape
from ui.estilo import aplicar_estilo

st.set_page_config(page_title="BillWatch", page_icon="static/favicon.png", layout="centered")
aplicar_estilo()
st.logo("static/logo.svg", size="medium")

pagina = st.navigation(
    [
        st.Page("paginas/subscricoes.py", title="Contas fixas", icon=":material/receipt_long:", default=True),
        st.Page("paginas/supermercado.py", title="Supermercado", icon=":material/shopping_cart:"),
        st.Page("paginas/luz.py", title="Luz", icon=":material/bolt:"),
        st.Page("paginas/sobre.py", title="Como funciona", icon=":material/help:"),
    ],
    position="top",
)
pagina.run()
rodape()
