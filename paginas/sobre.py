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
    'recorrentes, mas o dinheiro continua a ser teu, por isso não contam como custo.</li>'
    '<li><strong>Entre contas tuas</strong>: carregar a Revolut, a N26 ou a Wise, ou mandar dinheiro para outra '
    'conta no teu nome. Também não é um custo: o dinheiro só mudou de sítio.</li>'
    '<li><strong>A confirmar</strong>: pagamentos que só apareceram uma vez, como um seguro ou o Amazon Prime '
    'pagos uma vez por ano. Só entram no total se os confirmares em <em>Corrigir</em>.</li>'
    '<li><strong>Partes pagas por outros</strong>: se os colegas de casa te mandam todos os meses a parte deles '
    'da renda, da internet ou da luz, o total já é só a tua parte.</li></ul>')

st.subheader("Corrigir o talão", anchor=False)
st.markdown(
    "Ninguém conhece as tuas contas melhor do que tu. Em **Corrigir** podes retirar o que não é fixo, "
    "confirmar um pagamento anual, acrescentar à mão o que falta, dividir uma conta por várias pessoas e "
    "escrever o teu nome, para a app reconhecer as transferências para outras contas tuas. O nome fica só "
    "na sessão, tal como os ficheiros.")

st.subheader("Que ficheiros aceita", anchor=False)
st.markdown(
    "Extratos em CSV, Excel ou PDF, de qualquer banco: com colunas de débito e crédito ou com um só valor, "
    "com as datas escritas de qualquer forma, e vários ficheiros de uma vez, até de bancos diferentes "
    "(as transferências entre as tuas contas são emparelhadas e ficam de fora). Se um formato não for "
    "reconhecido, a app mostra a tabela e pedes-lhe tu que coluna é qual. Extratos de cripto ou de "
    "investimentos ficam de fora, porque não têm pagamentos de contas.")

st.subheader("O supermercado", anchor=False)
st.markdown(
    "O extrato diz onde compraste e quanto, mas não o quê. Por isso a página do supermercado mostra "
    "o que dá para saber com ele: quanto gastas por mês e em que cadeias, quantas idas fazes e quanto "
    "somam as idas pequenas, abaixo de 10 €. As bombas de gasolina das cadeias ficam de fora e as "
    "devoluções descontam. Para saber se mudar de cadeia compensa, a app usa o índice de preços que a "
    "DECO PROteste publica todos os anos para os supermercados online, que é uma média para um cabaz "
    "grande e não o teu carrinho.")

st.subheader("A luz", anchor=False)
st.markdown(
    "O custo de cada oferta é o termo fixo vezes os dias, mais o preço da energia vezes o consumo. "
    "A comparação é feita antes de IVA e taxas, que são quase iguais em todas as comercializadoras.")

st.subheader("Privacidade", anchor=False)
st.markdown(
    "Os ficheiros são lidos em memória, só para fazer as contas, e nunca são guardados. "
    "As fontes da app também são servidas pela própria app, sem pedidos a terceiros.")
