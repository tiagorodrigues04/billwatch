"""Peças visuais reutilizadas pelas páginas."""

from __future__ import annotations

import html
from dataclasses import dataclass

import altair as alt
import pandas as pd
import streamlit as st

from contas.recorrentes import euro

from .estilo import CORES

REPOSITORIO = "https://github.com/tiagorodrigues04/billwatch"


def cabecalho(titulo: str, introducao: str) -> None:
    st.title(titulo, anchor=False)
    st.html(f'<p class="bw-lead">{html.escape(introducao)}</p>')


def passos(lista: list[tuple[str, str]]) -> None:
    """Passos numerados — só para o que é mesmo uma sequência."""
    itens = "".join(f"<li><strong>{html.escape(t)}</strong>{html.escape(d)}</li>" for t, d in lista)
    st.html(f'<ol class="bw-passos">{itens}</ol>')


def discreto(texto: str) -> None:
    st.html(f'<p class="bw-discreto">{html.escape(texto)}</p>')


def rodape() -> None:
    st.html(f'<footer class="bw-rodape">BillWatch é um projeto de Ciência de Dados. Os ficheiros são lidos '
            f'em memória e nunca são guardados. <a href="{REPOSITORIO}" target="_blank">Código no GitHub</a>.</footer>')


# ---------------------------------------------------------------------------
# O talão
# ---------------------------------------------------------------------------

@dataclass
class Linha:
    nome: str
    valor: str
    estado: str = ""          # "" · "atencao" (marcador) · "parado" (riscado) · "total"
    nota: str = ""
    nota_alerta: bool = False  # nota a caneta vermelha


def talao(cabecalho_linhas: list[str], blocos: list[tuple[str | None, list[Linha]]], rodape_texto: str = "") -> None:
    """Desenha um talão: cabeçalho, blocos de linhas (com título opcional) e rodapé."""
    e = html.escape
    partes = ['<div class="bw-talao" role="table" aria-label="Talão">', '<div class="bw-t-cab">']
    if cabecalho_linhas:
        partes.append(f"<b>{e(cabecalho_linhas[0])}</b>")
        partes += [f"<span>{e(l)}</span>" for l in cabecalho_linhas[1:]]
    partes.append("</div>")
    for titulo, linhas in blocos:
        if titulo == "---":
            partes.append('<div class="bw-t-sep"></div>')
            continue
        if titulo:
            partes.append(f'<div class="bw-t-sec">{e(titulo)}</div>')
        for l in linhas:
            classe = f"bw-t-linha {'bw-t-total' if l.estado == 'total' else l.estado}".strip()
            partes.append(f'<div class="{classe}" role="row"><span class="bw-t-nome" role="cell">{e(l.nome)}</span>'
                          f'<span class="bw-t-pontos" aria-hidden="true"></span>'
                          f'<span class="bw-t-valor" role="cell">{e(l.valor)}</span></div>')
            if l.nota:
                partes.append(f'<div class="bw-t-nota{" caneta" if l.nota_alerta else ""}">{e(l.nota)}</div>')
    if rodape_texto:
        partes.append(f'<div class="bw-t-rodape">{e(rodape_texto)}</div>')
    partes.append("</div>")
    st.html("".join(partes))


# ---------------------------------------------------------------------------
# Gráfico
# ---------------------------------------------------------------------------

def barras(df: pd.DataFrame, categoria: str, valor: str, titulo_valor: str) -> None:
    """Barras horizontais de uma só série: tinta, pontas arredondadas, valor no fim de cada barra."""
    df = df.sort_values(valor, ascending=False).assign(_rotulo=lambda d: d[valor].map(euro))
    maximo = float(df[valor].max()) or 1.0
    base = alt.Chart(df).encode(
        y=alt.Y(f"{categoria}:N", sort="-x", title=None,
                axis=alt.Axis(labelColor=CORES["tinta"], labelFontSize=13, labelPadding=8, labelLimit=260,
                              ticks=False, domain=False)),
        x=alt.X(f"{valor}:Q", title=None, axis=None, scale=alt.Scale(domain=[0, maximo * 1.3], nice=False)),
        tooltip=[alt.Tooltip(f"{categoria}:N", title="Categoria"),
                 alt.Tooltip(f"{valor}:Q", title=titulo_valor, format=".2f")],
    )
    barras_ = base.mark_bar(color=CORES["tinta"], cornerRadiusEnd=4, height=16)
    rotulos = base.mark_text(align="left", dx=6, color=CORES["grafite"], fontSize=12).encode(text="_rotulo:N")
    grafico = (barras_ + rotulos).properties(height=36 * len(df) + 10).configure_view(stroke=None) \
        .configure(font="Schibsted Grotesk", background="transparent")
    st.altair_chart(grafico, width="stretch")
