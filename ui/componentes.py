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


def em_euros(df: pd.DataFrame, colunas: list[str]):
    """A tabela com os valores em euros escritos como no talão ("1 234,56 €", com vírgula).

    O formato das colunas do Streamlit (printf) só sabe escrever "1234.56". Com um Styler, a
    tabela mostra o texto em português mas os valores continuam a ser números: clicar no
    cabeçalho ordena pelo valor e não pelo texto. Nas column_config destas colunas não se
    põe "format", senão o Streamlit ignora o Styler.
    """
    return df.style.format(euro, subset=[c for c in colunas if c in df], na_rep="")


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


def talao_a_cinzento(onde=st, texto: str = "A ler os extratos…") -> None:
    """O talão ainda sem dados (um "skeleton"), no sítio onde o talão vai aparecer.

    Mostra-se enquanto os ficheiros são lidos e analisados, em vez de um spinner: a pessoa
    vê logo a forma do resultado. `onde` é o sítio (ex.: um st.empty() que depois recebe o talão).
    """
    def linha(nome: int, valor: int, extra: str = "") -> str:
        return (f'<div class="bw-t-linha{extra}"><span class="bw-esq" style="width:{nome}%"></span>'
                f'<span class="bw-t-pontos"></span><span class="bw-esq" style="width:{valor}%"></span></div>')

    linhas = "".join(linha(n, v) for n, v in [(44, 16), (30, 15), (38, 15), (50, 14), (34, 15), (41, 14)])
    onde.html(
        '<div class="bw-talao bw-esqueleto" role="status" aria-live="polite" aria-busy="true">'
        '<div class="bw-t-cab"><span class="bw-esq bw-esq-titulo"></span><span class="bw-esq" style="width:34%"></span>'
        '<span class="bw-esq" style="width:52%"></span></div>'
        f'{linhas}<div class="bw-t-sep"></div>{linha(36, 22, " bw-t-total")}'
        f'<div class="bw-t-rodape">{html.escape(texto)}</div></div>')


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
    nota_extra: str = ""       # segunda nota, sempre a lápis (ex.: "confirmado por ti", contas divididas)


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
            if l.nota_extra:
                partes.append(f'<div class="bw-t-nota">{e(l.nota_extra)}</div>')
    if rodape_texto:
        partes.append(f'<div class="bw-t-rodape">{e(rodape_texto)}</div>')
    partes.append("</div>")
    st.html("".join(partes))


# ---------------------------------------------------------------------------
# Gráfico
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, max_entries=32)
def _especificacao_barras(df: pd.DataFrame, categoria: str, valor: str, titulo_valor: str) -> dict:
    """O gráfico em Vega-Lite. Em cache: o Altair valida o gráfico todo a cada desenho (~25 ms por clique)."""
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
        .configure(font="Schibsted Grotesk Tabular", background="transparent")
    return grafico.to_dict()


def barras(df: pd.DataFrame, categoria: str, valor: str, titulo_valor: str) -> None:
    """Barras horizontais de uma só série: tinta, pontas arredondadas, valor no fim de cada barra."""
    st.vega_lite_chart(_especificacao_barras(df, categoria, valor, titulo_valor), width="stretch")


MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


@st.cache_data(show_spinner=False, max_entries=32)
def _especificacao_meses(df: pd.DataFrame, valor: str, titulo_valor: str) -> dict:
    df = df.assign(_mes=[f"{MESES[d.month - 1]} {d:%y}" for d in df["mes"]],
                   _rotulo=[f"{v:.0f}" for v in df[valor]],     # sem "€": no telemóvel as colunas são estreitas
                   _dica=df[valor].map(euro))
    maximo = float(df[valor].max()) or 1.0
    base = alt.Chart(df).encode(
        x=alt.X("_mes:N", sort=df["_mes"].tolist(), title=None,
                axis=alt.Axis(labelColor=CORES["grafite"], labelFontSize=12, labelAngle=0, labelOverlap=True,
                              ticks=False, domain=False)),
        y=alt.Y(f"{valor}:Q", title=None, axis=None, scale=alt.Scale(domain=[0, maximo * 1.2], nice=False)),
        tooltip=[alt.Tooltip("_mes:N", title="Mês"), alt.Tooltip("_dica:N", title=titulo_valor)],
    )
    colunas = base.mark_bar(color=CORES["tinta"], cornerRadiusEnd=4, width={"band": 0.62})
    rotulos = base.mark_text(baseline="bottom", dy=-4, color=CORES["grafite"], fontSize=10.5).encode(text="_rotulo:N")
    grafico = (colunas + rotulos).properties(height=220).configure_view(stroke=None) \
        .configure(font="Schibsted Grotesk Tabular", background="transparent")
    return grafico.to_dict()


def colunas_por_mes(df: pd.DataFrame, valor: str, titulo_valor: str) -> None:
    """Colunas mês a mês ("dez 25", "jan 26"…), com o valor arredondado por cima.

    `df["mes"]` é o primeiro dia de cada mês.
    """
    st.vega_lite_chart(_especificacao_meses(df, valor, titulo_valor), width="stretch")
