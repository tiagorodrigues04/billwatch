"""Identidade visual do BillWatch: "o talão".

Cores (só com significado, nunca decoração):
    papel     #EEF2F5  fundo da app, como o papel de um extrato
    folha     #FFFFFF  o talão
    tinta     #1B2B44  texto e ações
    grafite   #5B6B82  texto secundário
    marcador  #FFE45C  linha que merece atenção (como passar o marcador num extrato)
    caneta    #C62D2D  nota de alerta (como anotar a caneta vermelha)
Tipos: Schibsted Grotesk na interface; IBM Plex Mono só dentro do talão.
"""

from __future__ import annotations

import streamlit as st

CORES = {
    "papel": "#EEF2F5", "folha": "#FFFFFF", "tinta": "#1B2B44", "grafite": "#5B6B82",
    "linha": "#CBD4DF", "marcador": "#FFE45C", "caneta": "#C62D2D",
}

CSS = """
<style>
:root {
  --papel: #EEF2F5; --folha: #FFFFFF; --tinta: #1B2B44; --grafite: #5B6B82;
  --linha: #CBD4DF; --marcador: #FFE45C; --caneta: #C62D2D;
}

/* ---------- tipografia ---------- */
h1 { letter-spacing: -0.03em; line-height: 1.02 !important; }
h2, h3 { letter-spacing: -0.015em; }
.stMarkdown p, .stMarkdown li { max-width: 68ch; }

.bw-lead { font-size: 1.15rem; line-height: 1.5; color: var(--grafite); max-width: 54ch; margin: .5rem 0 2rem; }
.bw-discreto { color: var(--grafite); font-size: .9rem; }

/* ---------- passos: uma sequência real (1 → 2 → 3) ---------- */
.bw-passos { list-style: none; counter-reset: passo; display: grid; grid-template-columns: repeat(3, 1fr);
             gap: 1.25rem; padding: 0 !important; margin: 0 0 1.75rem !important; }
.bw-passos li { counter-increment: passo; border-top: 2px solid var(--tinta); padding-top: .65rem;
                font-size: .95rem; line-height: 1.45; color: var(--grafite); margin: 0; }
.bw-passos li::before { content: counter(passo); display: block; font-weight: 800; font-size: 1.4rem;
                        line-height: 1; color: var(--tinta); margin-bottom: .45rem; }
.bw-passos strong { display: block; color: var(--tinta); font-weight: 700; margin-bottom: .1rem; }
@media (max-width: 640px) { .bw-passos { grid-template-columns: 1fr; gap: .9rem; } }

/* ---------- zona de carregar ficheiros (em português) ---------- */
[data-testid="stFileUploaderDropzone"] { background: var(--folha); border: 1.5px dashed var(--grafite);
                                         border-radius: 10px; padding: 1.25rem; }
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p { font-size: 0; }
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {
  content: "Escolher ficheiros"; font-size: .9rem; }
[data-testid="stFileUploaderDropzoneInstructions"] > div > span { font-size: 0; }
[data-testid="stFileUploaderDropzoneInstructions"] > div > span::after {
  content: "ou arrasta-os para aqui"; font-size: .9rem; color: var(--grafite); }
[data-testid="stFileUploaderDropzone"][aria-label="Extratos do banco"] [data-testid="stFileUploaderDropzoneInstructions"] > div > span::after {
  content: "ou arrasta-os para aqui (CSV, Excel ou PDF)"; }
[data-testid="stFileUploaderDropzone"][aria-label="Fatura da luz"] button [data-testid="stMarkdownContainer"] p::after {
  content: "Escolher a fatura"; }
[data-testid="stFileUploaderDropzone"][aria-label="Fatura da luz"] [data-testid="stFileUploaderDropzoneInstructions"] > div > span::after {
  content: "ou arrasta-a para aqui (PDF)"; }
@media (max-width: 640px) {   /* no telemóvel não se arrasta ficheiros */
  [data-testid="stFileUploaderDropzoneInstructions"] { display: none; }
}

/* ---------- as marcas do talão, explicadas no texto ---------- */
.bw-ex-marcador { background: linear-gradient(transparent 10%, var(--marcador) 10%, var(--marcador) 90%, transparent 90%);
                  padding: 0 .2em; font-weight: 700; }
.bw-ex-riscado { text-decoration: line-through; text-decoration-color: var(--caneta); font-weight: 700; }
.bw-ex-caneta { color: var(--caneta); font-weight: 600; }
.bw-lista { padding-left: 1.2rem; margin: 0 0 1rem; max-width: 68ch; line-height: 1.6; }
.bw-lista li { margin-bottom: .45rem; }

/* ---------- o talão ---------- */
.bw-talao { position: relative; background: var(--folha); max-width: 470px; margin: .75rem 0 2.75rem;
            padding: 1.6rem 1.6rem 1.9rem; color: var(--tinta);
            font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: .85rem; line-height: 1.55;
            filter: drop-shadow(0 1px 1px rgba(27,43,68,.10)) drop-shadow(0 8px 18px rgba(27,43,68,.10));
            animation: bw-imprimir .6s cubic-bezier(.2,.7,.2,1) both; }
.bw-talao::after { content: ""; position: absolute; left: 0; right: 0; bottom: -11px; height: 12px;
                   background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20width%3D%2716%27%20height%3D%2712%27%20viewBox%3D%270%200%2016%2012%27%3E%3Cpath%20d%3D%27M0%200H16L8%2011Z%27%20fill%3D%27white%27%2F%3E%3C%2Fsvg%3E");
                   background-repeat: repeat-x; background-size: 16px 12px; }
@keyframes bw-imprimir { from { clip-path: inset(0 -40px 100% -40px); transform: translateY(-8px); }
                         to   { clip-path: inset(0 -40px -40px -40px); transform: none; } }
@media (prefers-reduced-motion: reduce) { .bw-talao { animation: none; } }

.bw-t-cab { text-align: center; margin-bottom: .9rem; }
.bw-t-cab b { display: block; font-family: "Schibsted Grotesk", sans-serif; font-weight: 800;
              font-size: 1.15rem; letter-spacing: -0.02em; margin-bottom: .15rem; }
.bw-t-cab span { display: block; color: var(--grafite); }
.bw-t-sep { border-top: 1.5px dashed var(--linha); margin: .8rem 0; }
.bw-t-sec { color: var(--grafite); margin: 1rem 0 .35rem; }
.bw-t-linha { display: flex; align-items: baseline; gap: .5rem; }
.bw-t-nome { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bw-t-pontos { flex: 1 1 1rem; min-width: 1rem; border-bottom: 1.5px dotted var(--linha); transform: translateY(-.3em); }
.bw-t-valor { white-space: nowrap; font-weight: 500; }
.bw-t-nota { font-family: "Schibsted Grotesk", sans-serif; font-size: .82rem; line-height: 1.35;
             color: var(--grafite); margin: .05rem 0 .5rem; }
.bw-t-nota.caneta { color: var(--caneta); font-weight: 600; }
.bw-t-linha.atencao .bw-t-nome { background: linear-gradient(transparent 10%, var(--marcador) 10%,
                                 var(--marcador) 90%, transparent 90%); padding: 0 .25em; margin-left: -.25em; }
.bw-t-linha.parado .bw-t-nome, .bw-t-linha.parado .bw-t-valor { text-decoration: line-through;
                                                                text-decoration-color: var(--caneta); color: var(--grafite); }
.bw-t-total { font-weight: 500; font-size: 1rem; margin-top: .1rem; }
.bw-t-total .bw-t-valor { font-weight: 500; font-size: 1.15rem; }
.bw-t-rodape { text-align: center; color: var(--grafite); margin-top: 1.1rem; font-size: .78rem; }

/* ---------- rodapé ---------- */
.bw-rodape { margin-top: 4rem; padding-top: 1rem; border-top: 1px solid var(--linha); color: var(--grafite);
             font-size: .85rem; }
.bw-rodape a { color: var(--tinta); }
</style>
"""

# O símbolo: um talão com dois olhos (watch) e uma linha marcada a amarelo.
SIMBOLO = """
<svg viewBox="0 0 26 32" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <path d="M2 2h22v26l-2.75-2.2-2.75 2.2-2.75-2.2-2.75 2.2-2.75-2.2L7.5 28l-2.75-2.2L2 28z"
        fill="#FFFFFF" stroke="#1B2B44" stroke-width="2" stroke-linejoin="round"/>
  <circle cx="9.5" cy="10" r="2.1" fill="#1B2B44"/>
  <circle cx="16.5" cy="10" r="2.1" fill="#1B2B44"/>
  <rect x="6.5" y="16" width="13" height="3" rx="1" fill="#FFE45C"/>
  <rect x="6.5" y="21" width="9" height="1.6" rx=".8" fill="#9AA7B8"/>
</svg>
"""


def aplicar_estilo() -> None:
    st.html(CSS)
