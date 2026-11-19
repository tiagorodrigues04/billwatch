"""Como funciona o BillWatch, em linguagem simples."""

from __future__ import annotations

import streamlit as st

from ui.componentes import cabecalho

cabecalho("Como funciona",
          "O BillWatch lê os movimentos da tua conta e procura os pagamentos que se repetem. "
          "Não precisa de acesso ao banco: só dos extratos que tu exportas.")

st.subheader("Encontrar as contas fixas", anchor=False)
st.markdown(
    "Cada movimento é atribuído a um serviço (Netflix, MEO, ginásio, renda…). Um serviço conta como fixo "
    "quando é pago com um ritmo regular, semanal, mensal, trimestral, semestral ou anual, e quase sempre "
    "pelo mesmo valor. A luz e a água podem variar, por isso entram pela média.")

st.subheader("O que fica marcado no talão", anchor=False)
st.html(
    '<ul class="bw-lista">'
    '<li><span class="bw-ex-marcador">Marcado a amarelo</span>, com uma <span class="bw-ex-caneta">nota a '
    'vermelho</span>: um preço que subiu, uma cobrança repetida em poucos dias, ou um valor de 1 € que pode ser '
    'um período experimental.</li>'
    '<li><span class="bw-ex-riscado">Riscado</span>: um serviço que deixou de ser cobrado. Não entra no total.</li>'
    '<li><strong>Poupança e investimento</strong>: transferências regulares para cofres, cripto ou PPR. São '
    'recorrentes, mas o dinheiro continua a ser teu, por isso não contam como custo.</li></ul>')

st.subheader("Que ficheiros aceita", anchor=False)
st.markdown(
    "Extratos em CSV, Excel ou PDF, de qualquer banco: com colunas de débito e crédito ou com um só valor, "
    "com as datas escritas de qualquer forma, e vários ficheiros de uma vez. Se um formato não for "
    "reconhecido, a app mostra a tabela e pedes-lhe tu que coluna é qual. Extratos de cripto ou de "
    "investimentos ficam de fora, porque não têm pagamentos de contas.")

st.subheader("A luz", anchor=False)
st.markdown(
    "O custo de cada oferta é o termo fixo vezes os dias, mais o preço da energia vezes o consumo. "
    "A comparação é feita antes de IVA e taxas, que são quase iguais em todas as comercializadoras.")

st.subheader("Privacidade", anchor=False)
st.markdown(
    "Os ficheiros são lidos em memória, só para fazer as contas, e nunca são guardados. "
    "As fontes da app também são servidas pela própria app, sem pedidos a terceiros.")
