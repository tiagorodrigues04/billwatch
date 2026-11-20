"""Extratos fictícios ROTULADOS para medir a qualidade da deteção.

Cada movimento traz a resposta certa na coluna "rotulo": o id da subscrição a que
pertence, ou "" se for uma despesa normal. Assim dá para contar acertos e erros.

Os extratos são gerados com regras diferentes das de contas/exemplo.py (que é a demo):
- várias pessoas, cada uma com um conjunto aleatório de subscrições e um período de 6 a 13 meses;
- descrições escritas de várias formas, como em bancos diferentes;
- dia de cobrança que varia (fins de semana, atrasos), subidas de preço, cancelamentos,
  serviços que começam a meio do extrato, cobranças duplicadas, valores em dólares;
- ruído difícil de propósito: combustível na Galp, MB WAY para amigos com valores redondos,
  compras de jogos ao mesmo preço, lojas com nomes parecidos com o catálogo e
  um corte de cabelo mensal a preço fixo (que tem padrão de subscrição mas não é uma).

Casos da vida real que enganavam a app até 20/11 (gerados à parte, com outro gerador
aleatório, para os extratos de antes ficarem iguais):
- dinheiro que só muda de conta: carregar a Revolut/Wise/N26 todos os meses e transferências
  para outra conta no nome do titular (rótulo "#entre": não são custos);
- pagamentos anuais que só aparecem uma vez no extrato (rótulo "#anual") e compras avulsas
  em lojas do catálogo, como um jogo na PlayStation Store (rótulo "#avulsa");
- contas divididas: colegas de casa que pagam a sua parte da renda, da internet ou da luz
  por MB WAY (coluna "partilha" = id da conta) e, para baralhar, uma mesada dos pais com o
  apelido do titular perto do dia da renda (que não é uma parte da renda).

Rótulos que começam por "#" nunca são subscrições.

Tudo é inventado. Os preços são plausíveis, não são tabelas oficiais.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import pandas as pd

FIM = pd.Timestamp("2026-10-31")
LOCAIS = ["COIMBRA", "LISBOA", "PORTO", "AVEIRO", "LEIRIA", "BRAGA"]


@dataclass
class Modelo:
    """Um tipo de subscrição: descrições possíveis, preços, periodicidade (dias)."""
    nome: str
    descricoes: list[str]
    precos: list[float]
    dias: float = 30.4
    variavel: bool = False      # consumo (luz, água): o valor muda todos os meses
    usd: bool = False           # cobrado em dólares: o valor em euros oscila um pouco com o câmbio


MODELOS = [
    Modelo("Netflix", ["COMPRA {n} NETFLIX.COM AMSTERDAM", "Pag. cartao Netflix.com", "NETFLIX.COM 866-579-7172"],
           [7.99, 11.99, 15.99]),
    Modelo("Spotify", ["COMPRA {n} SPOTIFY P{r} STOCKHOLM", "PAYPAL *SPOTIFY 35314369001", "Spotify AB"],
           [6.99, 11.99, 4.99]),
    Modelo("Disney+", ["COMPRA {n} DISNEY PLUS LONDON", "DisneyPlus"], [5.99, 9.99]),
    Modelo("HBO Max", ["MAX.COM HBO MAX", "COMPRA {n} HBO MAX"], [5.99, 9.99]),
    Modelo("YouTube Premium", ["GOOGLE *YOUTUBEPREMIUM g.co/helppay", "COMPRA {n} GOOGLE YOUTUBE PREMIUM"], [8.49, 12.99]),
    Modelo("Google One", ["GOOGLE ONE g.co/helppay", "GOOGLE *Google One"], [1.99, 2.99]),
    Modelo("iCloud", ["APPLE.COM/BILL ITUNES.COM", "COMPRA {n} APPLE.COM/BILL CORK"], [0.99, 2.99, 9.99]),
    Modelo("ChatGPT", ["OPENAI *CHATGPT SUBSCR SAN FRANCISCO", "COMPRA {n} OPENAI"], [20.0], usd=True),
    Modelo("Microsoft 365", ["MICROSOFT*365 PERSONAL", "COMPRA {n} MICROSOFT*STORE"], [7.0, 10.0]),
    Modelo("PlayStation Plus", ["PLAYSTATION NETWORK", "COMPRA {n} SONY INTERACTIVE ENT"], [8.99, 13.99]),
    Modelo("DAZN", ["COMPRA {n} DAZN LIMITED", "DAZN"], [19.99, 29.99]),
    Modelo("Sport TV", ["DD SPORT TV PORTUGAL REF {r}"], [22.90]),
    Modelo("MEO", ["DD MEO SA ENT 12345 REF {r}", "Cobranca SDD MEO - SERVICOS COMUNICACOES"], [35.0, 45.99, 59.99]),
    Modelo("NOS", ["DD NOS COMUNICACOES SA REF {r}"], [32.99, 49.99]),
    Modelo("Vodafone", ["DD VODAFONE PORTUGAL REF {r}"], [24.99, 39.99]),
    Modelo("DIGI", ["DD DIGI PORTUGAL LDA REF {r}"], [10.0, 15.0]),
    Modelo("EDP", ["DD EDP COMERCIAL REF {r}", "Cobranca SDD EDP COMERCIAL"], [45.0], variavel=True),
    Modelo("Galp (luz)", ["SDD GALP POWER SA {r}", "DD GALP ENERGIA REF {r}"], [40.0], variavel=True),
    Modelo("Goldenergy", ["DD GOLDENERGY REF {r}"], [38.0], variavel=True),
    Modelo("Água", ["DD AGUAS DE COIMBRA EM REF {r}", "DD AGUAS DO PORTO EM {r}"], [22.0], dias=61, variavel=True),
    Modelo("Fitness Hut", ["DD FITNESS HUT {local} REF {r}"], [29.99, 34.99]),
    Modelo("Solinca", ["DD SOLINCA HEALTH FITNESS {r}"], [39.90]),
    Modelo("Fidelidade", ["DD FIDELIDADE SEGUROS APOLICE {r}"], [84.50, 120.30], dias=182),
    Modelo("Médis", ["DD MEDIS SEGUROS SAUDE {r}"], [29.50]),
    Modelo("Renda", ["TRF RENDA QUARTO REF {r}", "Trf Imediata Sepa+ RENDA {mes}"], [250.0, 300.0, 380.0]),
    Modelo("Condomínio", ["DD CONDOMINIO EDIFICIO {r}"], [90.0], dias=91),
    Modelo("Propinas", ["PAG PROPINAS ISCAC REF {r}"], [69.70]),
    # Fora do catálogo: a app só os pode encontrar pelo padrão (precisa de 3 pagamentos).
    Modelo("Natação", ["DD CLUBE NATACAO MONDEGO {r}"], [25.0, 32.0]),
    Modelo("Explicações", ["TRF EXPLICACOES MATEMATICA"], [80.0, 120.0]),
    Modelo("Patreon", ["COMPRA {n} PATREON MEMBERSHIP"], [5.0, 8.0], usd=True),
    Modelo("Notion", ["NOTION LABS INC SAN FRANCISCO"], [10.0], usd=True),
    Modelo("Quotas AAC", ["DD ASSOCIACAO ACADEMICA QUOTAS {r}"], [15.0], dias=91),
]

POR_ANO = {7: 52, 30.4: 12, 61: 6, 91: 4, 182: 2, 365: 1}


@dataclass
class Verdade:
    """A resposta certa para uma subscrição de uma pessoa."""
    id: str
    nome: str
    n_pagamentos: int
    custo_mensal: float
    ativa: bool
    subiu_preco: bool
    no_catalogo: bool = field(default=True)
    partilha_mensal: float = 0.0     # quanto pagam os outros por mês (contas divididas)


def _no_catalogo(nome: str) -> bool:
    return nome not in {"Natação", "Explicações", "Patreon", "Notion", "Quotas AAC"}


def _preencher(rng: random.Random, modelo: str, local: str) -> str:
    return (modelo.replace("{n}", str(rng.randint(1000, 9999)))
            .replace("{r}", str(rng.randint(10**8, 10**9 - 1)))
            .replace("{local}", local)
            .replace("{mes}", rng.choice(["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT"])))


def _dia_util(d: pd.Timestamp) -> pd.Timestamp:
    """Débitos que calham ao fim de semana passam para segunda-feira."""
    while d.weekday() >= 5:
        d += pd.Timedelta(days=1)
    return d


def _subscricoes(rng: random.Random, inicio: pd.Timestamp, pessoa: int, local: str):
    movimentos, verdades = [], []
    escolhidos = rng.sample(MODELOS, rng.randint(4, 11))
    for k, m in enumerate(escolhidos):
        sid = f"p{pessoa}-{k}"
        preco = rng.choice(m.precos)
        descricao_fixa = rng.choice(m.descricoes)   # cada pessoa vê sempre o mesmo formato
        # começa antes do extrato (o normal) ou a meio
        comeco = inicio - pd.Timedelta(days=rng.randint(0, 60)) if rng.random() < 0.8 else \
            inicio + pd.Timedelta(days=rng.randint(20, 120))
        cancela = rng.random() < 0.15
        fim_sub = FIM - pd.Timedelta(days=rng.randint(int(m.dias * 2.2), int(m.dias * 4))) if cancela else FIM
        subida_em = comeco + pd.Timedelta(days=rng.randint(60, 240)) if (not m.variavel and rng.random() < 0.2) \
            else None
        novo_preco = round(preco * rng.uniform(1.10, 1.30), 2)

        pagamentos, valores = [], []
        n = 0
        while True:
            alvo = comeco + pd.Timedelta(days=round(n * m.dias))
            n += 1
            if alvo > fim_sub:
                break
            data = alvo + pd.Timedelta(days=rng.choice([0, 0, 0, 1, 2, 3]))
            if "DD" in descricao_fixa or "SDD" in descricao_fixa:
                data = _dia_util(data)
            if data < inicio or data > FIM:
                continue
            valor = novo_preco if subida_em is not None and data >= subida_em else preco
            if m.variavel:
                inverno = abs(6.5 - data.month) / 5.5           # mais caro no inverno
                valor = preco * (0.75 + 0.5 * inverno) * rng.uniform(0.9, 1.1)
            if m.usd:
                valor = valor * rng.uniform(0.86, 0.94)          # câmbio USD -> EUR
            valor = round(valor, 2)
            pagamentos.append(data)
            valores.append(valor)
            movimentos.append((data, _preencher(rng, descricao_fixa, local), -valor, sid))
            if rng.random() < 0.02:                              # cobrança duplicada
                movimentos.append((data + pd.Timedelta(days=rng.randint(1, 3)),
                                   _preencher(rng, descricao_fixa, local), -valor, sid))

        if len(pagamentos) < 2:   # com um só pagamento ninguém consegue provar que se repete
            continue
        por_ano = POR_ANO[m.dias]
        tipico = sum(valores[-3:]) / len(valores[-3:]) if (m.variavel or m.usd) else valores[-1]
        ativa = (FIM - pagamentos[-1]).days <= m.dias * 1.5
        subiu = subida_em is not None and valores[0] < valores[-1]
        verdades.append(Verdade(sid, m.nome, len(pagamentos), round(tipico * por_ano / 12, 2), ativa, subiu,
                                _no_catalogo(m.nome)))
    return movimentos, verdades


def _ruido(rng: random.Random, inicio: pd.Timestamp, local: str):
    """Despesas normais. Algumas parecem subscrições de propósito."""
    mov = []
    dias = pd.date_range(inicio, FIM, freq="D")

    def add(data, desc, valor):
        mov.append((data, desc, -round(valor, 2), ""))

    tem_carro = rng.random() < 0.45
    posto = rng.choice(["GALP", "REPSOL", "PRIO", "BP"])
    corta_cabelo = rng.random() < 0.2
    for d in dias:
        if rng.random() < 0.22:
            add(d, f"COMPRA {rng.randint(1000, 9999)} {rng.choice(['CONTINENTE', 'PINGO DOCE', 'LIDL', 'MERCADONA'])} "
                   f"{local}", rng.uniform(4, 85))
        if rng.random() < 0.5:
            add(d, f"COMPRA {rng.randint(1000, 9999)} {rng.choice(['CAFE CENTRAL', 'PASTELARIA SAO JOSE', 'TASCA DO ZE'])}",
                rng.uniform(0.7, 9))
        if tem_carro and rng.random() < 0.06:
            add(d, f"COMPRA {rng.randint(1000, 9999)} {posto} {local}", rng.uniform(25, 60))
        if rng.random() < 0.06:
            add(d, "COMPRA UBER *TRIP HELP.UBER.COM" if rng.random() < 0.5 else "BOLT.EU/R/2605", rng.uniform(3, 15))
        if rng.random() < 0.05:   # MB WAY para amigos: valores redondos que se repetem por acaso
            amigo = rng.choice(["JOAO SEGURO", "ANA RENDA", "MIGUEL SANTOS", "RITA COSTA", "PEDRO GYM"])
            add(d, f"MB WAY PARA {amigo}", rng.choice([5, 10, 10, 15, 20, 20, 25]))
        if rng.random() < 0.02:   # compras online, às vezes ao mesmo preço
            loja = rng.choice(["STEAM PURCHASE", "GOOGLE PLAY APPS", "AMAZON.ES MKTP", "WORTEN ONLINE"])
            add(d, f"COMPRA {rng.randint(1000, 9999)} {loja}", rng.choice([4.99, 9.99, 19.99, rng.uniform(5, 60)]))
        if rng.random() < 0.01:   # lojas com nomes que lembram o catálogo
            loja = rng.choice(["LOJA DAS PRENDAS", "GYMSHARK STORE", "RESTAURANTE AGUAS FURTADAS",
                               "DISNEYLAND PARIS", "FARMACIA CENTRAL"])
            add(d, f"COMPRA {rng.randint(1000, 9999)} {loja}", rng.uniform(5, 70))
    if corta_cabelo:   # corte de cabelo a preço fixo de 4 em 4/5 semanas
        d = inicio + pd.Timedelta(days=rng.randint(0, 20))
        while d <= FIM:
            add(d, f"COMPRA {rng.randint(1000, 9999)} BARBEARIA DO BAIRRO", 12.0)
            d += pd.Timedelta(days=rng.randint(28, 38))
    return mov


# ---------------------------------------------------------------------------
# Casos novos: entre contas, anuais e contas divididas
# ---------------------------------------------------------------------------

TITULAR_NOMES = ["TIAGO", "MARTA", "RUI", "INES", "SOFIA", "BEATRIZ", "DIOGO", "CAROLINA"]
TITULAR_APELIDOS = ["RODRIGUES", "FERREIRA", "MARTINS", "SOUSA", "PEREIRA", "OLIVEIRA", "CARVALHO", "PINTO"]
COLEGAS_NOMES = ["JOAO", "ANA", "RITA", "PEDRO", "LUIS", "CATARINA", "FILIPE", "MARIANA"]
COLEGAS_APELIDOS = ["SILVA", "COSTA", "SANTOS", "GOMES", "LOPES", "MARQUES", "RIBEIRO"]   # nunca os do titular
PARTILHAVEIS = {"Renda", "MEO", "NOS", "Vodafone", "DIGI", "EDP", "Galp (luz)", "Goldenergy", "Água",
                "Netflix", "Spotify"}
CARREGAMENTOS = ["TRF IMEDIATA P/ REVOLUT", "COMPRA {n} REVOLUT**{n}* DUBLIN", "WISE EUROPE SA BRUXELAS",
                 "Trf Imediata Sepa+ N26"]
PARA_TI = ["TRF P/ {T}", "TRF IMEDIATA PARA {T}", "Transferencia para {t}"]
ANUAIS = [  # (modelo, nome de um modelo mensal com o mesmo nome no catálogo, que não pode coexistir)
    (Modelo("Amazon Prime (anual)", ["AMAZON PRIME*{r}", "AMZN PRIME PT"], [49.90], dias=365), None),
    (Modelo("Seguro automóvel (anual)", ["DD LOGO SEGUROS AUTOMOVEL {r}", "DD OK TELESEGUROS APOLICE {r}"],
            [312.40, 268.90, 189.50], dias=365), None),
    (Modelo("Microsoft 365 (anual)", ["MICROSOFT*365 FAMILY ANUAL"], [99.0], dias=365), "Microsoft 365"),
    (Modelo("Duolingo (anual)", ["DUOLINGO *SUPER ANUAL"], [83.99], dias=365), None),
]
AVULSAS = [("PLAYSTATION NETWORK", [69.99, 39.99], "PlayStation Plus"),
           ("COMPRA {n} NINTENDO ESHOP", [59.99, 19.99], None),
           ("XBOX STORE {n}", [29.99, 69.99], None)]


@dataclass
class Caso:
    extrato: pd.DataFrame      # data, descricao, valor, rotulo, partilha
    verdades: list[Verdade]
    titular: str               # o nome da pessoa (para reconhecer transferências para contas dela)


def _todos_os_meses(rng: random.Random, inicio: pd.Timestamp, valor_dia: int):
    """Um dia por mês (com 0 a 2 dias de atraso), do início do extrato até ao fim."""
    for periodo in pd.period_range(inicio, FIM, freq="M"):
        d = pd.Timestamp(year=periodo.year, month=periodo.month, day=valor_dia) + \
            pd.Timedelta(days=rng.choice([0, 0, 1, 2]))
        if inicio <= d <= FIM:
            yield d


def _casos_novos(rng: random.Random, inicio: pd.Timestamp, local: str, titular: str,
                 subs: list[tuple], verdades: list[Verdade]) -> list[tuple]:
    mov: list[tuple] = []
    nomes = {v.nome for v in verdades}
    apelido = titular.split()[-1]

    if rng.random() < 0.35:   # carregar a Revolut (ou outra conta digital) todos os meses
        desc, valor = rng.choice(CARREGAMENTOS), rng.choice([50.0, 100.0, 150.0, 200.0])
        for d in _todos_os_meses(rng, inicio, rng.randint(1, 28)):
            mov.append((d, _preencher(rng, desc, local), -valor, "#entre", ""))
    if rng.random() < 0.20:   # mandar dinheiro para outra conta no próprio nome
        desc = rng.choice(PARA_TI).replace("{T}", titular).replace("{t}", titular.title())
        valor = rng.choice([100.0, 150.0, 250.0, 300.0])
        for d in _todos_os_meses(rng, inicio, rng.randint(1, 28)):
            mov.append((d, desc, -valor, "#entre", ""))

    meses = (FIM - inicio).days / 30.4
    if meses <= 11.5 and rng.random() < 0.35:   # um pagamento anual (só cabe uma vez no extrato)
        opcoes = [m for m, conflito in ANUAIS if conflito not in nomes]
        m = rng.choice(opcoes)
        d = inicio + pd.Timedelta(days=rng.randint(10, (FIM - inicio).days - 10))
        mov.append((d, _preencher(rng, rng.choice(m.descricoes), local), -rng.choice(m.precos), "#anual", ""))
    if rng.random() < 0.30:   # uma compra avulsa numa loja do catálogo (não é anual nem subscrição)
        opcoes = [a for a in AVULSAS if a[2] not in nomes]
        desc, precos, _ = rng.choice(opcoes)
        d = inicio + pd.Timedelta(days=rng.randint(5, (FIM - inicio).days - 5))
        mov.append((d, _preencher(rng, desc, local), -rng.choice(precos), "#avulsa", ""))

    # Contas divididas: colegas de casa pagam a sua parte de uma conta que sai da conta do titular.
    pagamentos: dict[str, list] = {}
    for data, _, valor, sid in subs:
        pagamentos.setdefault(sid, []).append((data, -valor))
    partilhaveis = [v for v in verdades if v.nome in PARTILHAVEIS and v.ativa]
    if partilhaveis and rng.random() < 0.45:
        v = rng.choice(partilhaveis)
        k = rng.choice([2, 2, 3, 4])
        colegas = rng.sample([f"{n} {a}" for n in COLEGAS_NOMES for a in COLEGAS_APELIDOS], k - 1)
        for colega in colegas:
            desc = rng.choice(["MB WAY DE {X}", "TRF DE {X}", "TRF IMEDIATA DE {X}"]).replace("{X}", colega)
            for data, valor in sorted(pagamentos[v.id]):
                if rng.random() < 0.08:          # um mês em que se esqueceu de pagar
                    continue
                d = data + pd.Timedelta(days=rng.randint(-2, 5))
                if inicio <= d <= FIM:
                    mov.append((d, desc, round(valor / k, 2), "", v.id))
        v.partilha_mensal = round(v.custo_mensal * (k - 1) / k, 2)
    renda = [v for v in verdades if v.nome == "Renda"]
    if renda and rng.random() < 0.30:   # a mesada dos pais, perto do dia da renda (não é uma parte da renda)
        pai = f"{rng.choice(['MARIA', 'PAULO', 'ISABEL', 'JORGE'])} {apelido}"
        valor = round(pagamentos[renda[0].id][0][1] * rng.uniform(0.3, 0.55) / 10) * 10
        for data, _ in sorted(pagamentos[renda[0].id]):
            mov.append((data + pd.Timedelta(days=rng.randint(-3, 2)), f"TRF DE {pai}", float(valor), "", ""))
    return mov


def gerar_caso(pessoa: int, semente: int = 0) -> Caso:
    """Um extrato rotulado, as subscrições verdadeiras e o nome do titular."""
    rng = random.Random(semente * 100_003 + pessoa)
    meses = rng.randint(6, 13)
    inicio = (FIM - pd.DateOffset(months=meses)).normalize() + pd.Timedelta(days=1)
    local = rng.choice(LOCAIS)
    subs, verdades = _subscricoes(rng, inicio, pessoa, local)
    mov = subs + _ruido(rng, inicio, local)
    mov.append((inicio + pd.Timedelta(days=2), "TRF SALARIO / MESADA", 900.0, ""))
    mov = [m + ("",) for m in mov]

    outro = random.Random((semente * 100_003 + pessoa) * 31 + 7)   # não mexe nos extratos de antes
    titular = f"{outro.choice(TITULAR_NOMES)} {outro.choice(TITULAR_APELIDOS)}"
    mov += _casos_novos(outro, inicio, local, titular, subs, verdades)
    extrato = pd.DataFrame(mov, columns=["data", "descricao", "valor", "rotulo", "partilha"])
    return Caso(extrato.sort_values("data", kind="stable").reset_index(drop=True), verdades, titular)


def gerar_pessoa(pessoa: int, semente: int = 0) -> tuple[pd.DataFrame, list[Verdade]]:
    """Um extrato rotulado (data, descricao, valor, rotulo, partilha) e as subscrições verdadeiras."""
    caso = gerar_caso(pessoa, semente)
    return caso.extrato, caso.verdades
