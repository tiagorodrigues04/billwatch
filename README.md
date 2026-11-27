# 👀 BillWatch

**Descobre quanto pagas todos os meses e onde estás a pagar a mais.**

Carregas o extrato do banco e a app encontra sozinha as subscrições e contas fixas
(Netflix, ginásio, MEO, renda...), diz-te quanto isso dá por mês e por ano e avisa-te
quando um preço sobe, quando há uma cobrança duplicada ou quando um serviço parou de
ser cobrado. Não conta como custo o dinheiro que só muda de conta (carregar a Revolut),
desconta o que os colegas de casa te pagam da renda ou da internet e guarda para
confirmares os pagamentos que só aparecem uma vez por ano. Com os mesmos extratos, mostra
quanto gastas no supermercado, em que cadeias e quanto pesam as idas pequenas. Também lê
a fatura da luz em PDF e compara-a com outras ofertas.

Inspirado no Rocket Money (EUA), adaptado a bancos e serviços portugueses.
Feito em Python (pandas, pdfplumber) e Streamlit.

**▶ Experimenta online: [billwatch-pt.streamlit.app](https://billwatch-pt.streamlit.app/)** (abre com um extrato de exemplo, não é preciso carregar dados reais)

**▶ Ou no teu browser, sem servidor: [tiagorodrigues04.github.io/billwatch](https://tiagorodrigues04.github.io/billwatch/)** (os extratos não saem do computador; a primeira vez pode demorar um minuto a abrir)

<p align="center"><img src="docs/talao.png" alt="Talão do BillWatch com as contas fixas de um extrato de exemplo: renda, luz, MEO, ginásio, ChatGPT, seguro, Netflix com aviso de subida de preço, Spotify com aviso de cobrança repetida e Disney+ riscado por já não ser cobrado" width="420"></p>

## Resultados

A deteção foi medida em **1000 extratos fictícios rotulados** (6 a 13 meses cada, 7301
subscrições). Os extratos têm de propósito os casos difíceis: abastecimentos na Galp,
MB WAY para amigos com valores redondos, compras de jogos ao mesmo preço, serviços
cobrados em dólares, subidas de preço, cancelamentos e cobranças duplicadas. Desde 20/11
têm também três casos da vida real que enganavam a app: **carregamentos da Revolut e
transferências para outras contas do titular**, **pagamentos anuais** que só aparecem uma
vez no extrato e **contas divididas** com colegas de casa (ver [Avaliação](#avaliação)).

| Métrica | Antes (20/11) | Atual |
|---|---|---|
| **Precisão** (quando diz que é subscrição, acerta) | 90,8% | **97,4%** |
| **Recall** (das subscrições que existem, quantas encontra) | 99,9% | **99,9%** |
| Erro médio no custo por mês | 0,04 € | 0,04 € |
| Subidas de preço avisadas | 95,2% | 95,2% |
| Avisos de subida falsos | 1 | 1 |
| Ativa / cancelada certa | 100% | 100% |

| Caso da vida real | Antes (20/11) | Atual |
|---|---|---|
| Linhas de custo que eram dinheiro entre contas tuas (475 extratos com esses movimentos) | 541 | **0** |
| Pagamentos anuais com 1 só pagamento que aparecem no talão (240) | 0% | **100%**, em "A confirmar" |
| Contas divididas com as partes dos colegas descontadas (429) | 0% | **100%** |
| Erro médio na tua parte, nas contas divididas | 33,34 € | **0,03 €** |
| Descontos falsos (contas que ninguém divide) | 0 | 0 |

Na coluna "Atual", a pessoa escreveu o nome em *Corrigir → Contas tuas*. Sem o nome, as
transferências para outra conta no nome dela continuam a contar como custo (208 linhas,
precisão de 94,8%) e uma mesada dos pais perto do dia da renda passa por uma parte da renda
(49 descontos falsos, que se desligam um a um em *Corrigir → Dividir*). Das linhas em
"A confirmar", 56% são mesmo pagamentos fixos (anuais ou subscrições que começaram agora);
as outras são compras avulsas em lojas do catálogo, como um jogo na PlayStation Store, que
pela data não se distinguem de um pagamento anual. Por isso ficam a confirmar e não entram
no total. A primeira versão (19/11), medida só com os casos difíceis de então, tinha 86,0% de
precisão.

---

## Como correr

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
streamlit run app.py               # abre em http://localhost:8501
pytest                             # ~200 testes
ruff check .                       # verifica o código (também corre no GitHub)
python -m avaliacao.avaliar        # mede a qualidade da deteção
```

A app arranca com um **extrato de exemplo** (12 meses fictícios de um estudante), por
isso dá para experimentar logo sem dados reais. Os testes correm sozinhos no GitHub a
cada alteração (separador *Actions*).

## Versão no browser

A mesma app corre sem servidor em
[tiagorodrigues04.github.io/billwatch](https://tiagorodrigues04.github.io/billwatch/). O
[stlite](https://github.com/whitphx/stlite) põe o Streamlit e o Python a correr dentro da
página ([Pyodide](https://pyodide.org): Python compilado para WebAssembly), por isso os
extratos são lidos no browser e **nunca saem do computador**. Da internet só vem código: o
Python e as bibliotecas, da jsDelivr e do PyPI, na primeira vez que se abre.

A página é gerada por `ferramentas/construir_pagina.py`, que mete o código da app, os dados
e o tema (com as letras) num único HTML. Sempre que o `main` muda, o GitHub Actions volta a
gerá-la e publica-a no GitHub Pages (ramo `gh-pages`). Para a gerar à mão:

```bash
python ferramentas/construir_pagina.py _site    # _site/index.html também abre diretamente do disco
```

Diferenças em relação à app online: o pdfplumber é instalado sem o pypdfium2 (só serve para
desenhar páginas como imagem e não existe para o browser), e os textos sobre privacidade
dizem que os ficheiros não saem do computador.

## Formatos de extrato suportados

| Tipo | O que a app percebe |
|---|---|
| **CSV** | separador `;` `,` tab ou `\|` · codificação UTF-8 ou Windows · linhas de título antes da tabela · vários blocos no mesmo ficheiro (ex.: Revolut: resumo + conta + cripto) |
| **Excel** | `.xlsx`, `.xls` antigo e `.xls` que na verdade é HTML · datas reais ou em número série · títulos antes da tabela |
| **PDF** | com grelha ou só texto · colunas Débito/Crédito, "Dinheiro retirado/recebido", "Money out/in" ou um só "Montante" · do mais antigo para o mais recente ou ao contrário · várias secções e páginas · descrições em 2 linhas · data só na 1.ª linha de cada dia · PDFs com letras estragadas (`(cid:231)`) |
| **Valores** | `1.234,56` `1,234.56` `-9,99` `9,99-` `(9,99)` `+9,99` `9,99 D/C` `€9.99` `9,99 €` `1 234,56` · ou valor positivo com coluna D/C |
| **Datas** | `05-10-2026` `05/10/26` `05.10.2026` `2026-10-05` `5 out 2026` `5 de out. de 2026` `Oct 5, 2026` · e sem ano (`05.10`), com o ano tirado do período do extrato |
| **Limpeza** | movimentos revertidos/recusados saem · só a moeda principal (EUR) · linhas de saldo inicial/final e totais saem · ficheiros repetidos ou sobrepostos não duplicam, mesmo em formatos diferentes do mesmo banco (o PDF corta descrições, o CSV acrescenta pormenores) · com extratos de bancos diferentes, as transferências entre as tuas contas são emparelhadas e não contam como custo |
| **Não é um extrato da conta** | extratos de cripto/investimentos (colunas Quantidade/Preço, tickers como BTC, ETH, SOL) são reconhecidos e ficam de fora, com uma explicação |

**Verificação de qualidade.** Cada leitura é verificada antes de entrar na análise: se a
maioria dos movimentos não tiver descrição, se as saídas forem mais de 10× as entradas
(ou o contrário) ou se houver muitos valores repetidos sem descrição, o ficheiro fica de
fora com um aviso a explicar porquê — em vez de aparecerem números absurdos. O
utilizador pode corrigir as colunas (CSV/Excel) ou decidir usá-lo mesmo assim.
No PDF, o leitor experimenta várias estratégias (tabelas desenhadas, colunas pelo
cabeçalho, só texto) e fica com a mais coerente: descrições preenchidas e saldo a bater certo.

**Se um formato não for reconhecido**, a app não fica presa: mostra a tabela e pede ao
utilizador que diga que coluna é a data, a descrição e o valor (já com um palpite
feito pelo conteúdo). Há também a opção *Inverter sinais*, e um **diagnóstico anónimo**
(letras → `x`, números → `9`) que se pode partilhar para corrigir o leitor sem expor dados.

Está tudo testado em `tests/formatos/`: 18 extratos fictícios que imitam formas reais de
exportar, todos gerados a partir dos mesmos movimentos — e o teste exige que todos deem
**exatamente** os mesmos movimentos, comerciantes e resultado final. Há ainda 3 ficheiros
"especiais" (cripto em PDF e CSV, e um PDF ilegível) que têm de ficar de fora com aviso.
Para acrescentar um formato novo: imitá-lo em `tests/gerar_formatos.py` e correr
`python tests/gerar_formatos.py`.

## Estrutura

```
app.py                  Configuração, estilo e navegação entre páginas
paginas/
  subscricoes.py        Carregar extratos e ver o talão das contas fixas
  supermercado.py       Quanto gastas no supermercado, com os mesmos extratos
  luz.py                Ler a fatura da luz e comparar ofertas
  sobre.py              Como funciona, em linguagem simples
ui/
  estilo.py             Identidade visual (cores, CSS do talão e do talão a cinzento)
  componentes.py        Peças visuais: talão, talão a cinzento, passos, gráfico, rodapé
  leitura.py            Ler os ficheiros carregados, com plano B se o formato for desconhecido
  dados.py              Leituras e análise com cache (os cliques não repetem as contas)
  extratos.py           Os extratos carregados, partilhados entre as páginas
contas/                 A lógica, sem Streamlit (testável à parte)
  texto.py              Ler números e datas escritos de qualquer forma; anonimizar
  extrato.py            CSV/Excel/HTML → tabela → (data, descricao, valor); nome do comerciante
  leitor_pdf.py         Extratos em PDF (várias estratégias, fica a mais coerente)
  catalogo.py           Comerciantes conhecidos em PT → nome e categoria
  recorrentes.py        Deteção de pagamentos recorrentes + alertas; "A confirmar" (anuais)
  entre_contas.py       Dinheiro que só muda de conta: nome do titular e pares entre extratos
  partilhas.py          Contas divididas: quem te paga parte de uma conta, e a tua parte
  supermercados.py      Compras por cadeia, idas pequenas e o índice de preços da DECO
  energia.py            Fatura da luz e comparação de ofertas
  exemplo.py            Extrato fictício da demo e dos testes
avaliacao/              Medir a qualidade da deteção
  gerar.py              Extratos fictícios rotulados (cada movimento sabe se é subscrição)
  avaliar.py            Precisão, recall, erro no custo, alertas e os três casos da vida real
static/                 Logótipo, favicon e fontes (servidos pela própria app)
ferramentas/
  fonte_tabular.py      Gera a fonte da interface com algarismos tabulares
  construir_pagina.py   Gera a versão que corre no browser (stlite), para o GitHub Pages
  pagina.html           Modelo dessa página: ecrã de arranque e arranque do stlite
.streamlit/config.toml  Tema: cores, fontes e tamanhos
dados/                  Ofertas de luz (VALORES DE EXEMPLO), índice de preços dos supermercados
                        (DECO PROteste, 2025) e uma fatura fictícia
tests/                  Testes da lógica, dos formatos, da interface e da qualidade mínima
  cenarios.py           Extratos pequenos com os casos entre contas, anuais e contas divididas
docs/                   Imagens do README
.github/workflows/      Corre os testes a cada alteração e publica a versão no browser
```

## Design

A ideia central é **o talão**: o resultado aparece como um talão de Multibanco, com cada
conta fixa numa linha e o total por mês no fundo. As cores só aparecem quando significam
alguma coisa:

| Cor | Significa |
|---|---|
| Papel `#EEF2F5` e tinta `#1B2B44` | a base: fundo e texto |
| Marcador `#FFE45C` | uma linha que merece atenção, como passar o marcador num extrato |
| Caneta vermelha `#C62D2D` | a nota que explica o alerta (preço subiu, cobrança repetida…) |
| Riscado a vermelho | um serviço que deixou de ser cobrado |

Tipos de letra: **Schibsted Grotesk** na interface e **IBM Plex Mono** só dentro do talão.
São servidos pela própria app (`static/fontes`, licença OFL), sem pedidos a terceiros.

Detalhes que fazem a app parecer mais cuidada:
- **Algarismos tabulares**: todos os algarismos têm a mesma largura, por isso os valores
  alinham em coluna (as vírgulas de 577,16 € e de 540,00 € ficam umas por baixo das outras).
  As tabelas do Streamlit são desenhadas num canvas, onde o CSS `tabular-nums` não chega,
  por isso a app usa uma cópia da Schibsted Grotesk com os algarismos tabulares por omissão
  (`ferramentas/fonte_tabular.py`; só mudam os algarismos, a pontuação fica igual).
- **Euros com vírgula também nas tabelas**: o formato das colunas do Streamlit só escreve
  "1234.56", por isso as tabelas usam o mesmo formato do talão ("1 234,56 €") através de um
  `Styler`, e continuam a ordenar pelo valor.
- **Títulos equilibrados**: os títulos partem-se em linhas de tamanho parecido
  (`text-wrap: balance`) e os parágrafos não acabam com uma palavra sozinha (`text-wrap: pretty`).
- **Talão a cinzento**: enquanto os extratos são lidos, aparece a forma do talão no sítio
  onde ele vai ficar, em vez de um spinner. Sem animação para quem a desligou no sistema.
- **Cliques rápidos**: o Streamlit volta a correr a página a cada clique; a junção dos
  extratos, a deteção e o gráfico ficam em cache, por isso um clique no "Corrigir" não repete
  as contas (com 3 extratos juntos, de 519 ms para 172 ms; com o exemplo, de 202 para 78 ms).

## Como funciona

### 1. Ler o extrato (`extrato.py`, `leitor_pdf.py`, `texto.py`)
Cada banco exporta de forma diferente (ver a tabela acima). A leitura tem 3 passos:
1. **Ficheiro → linhas de células.** O separador do CSV escolhe-se pela consistência
   (o que dá o mesmo nº de colunas em mais linhas).
2. **Linhas → tabela.** Procuram-se *todas* as linhas que parecem cabeçalhos de
   movimentos (têm uma célula de data e uma de valor), lê-se o bloco depois de cada uma
   e juntam-se os blocos com as mesmas colunas. É assim que o resumo da Revolut fica de
   fora e os cabeçalhos repetidos em cada página de um PDF não estragam nada.
3. **Tabela → que coluna é qual**, pelo nome (cuidado: "Data Valor" é uma data!) e,
   se o nome não ajudar, pelo conteúdo (a coluna com mais datas válidas é a data).

**PDFs** não têm colunas — só palavras com coordenadas. O leitor agrupa as palavras em
linhas, encontra o cabeçalho e guarda a **posição horizontal** de cada coluna; cada
valor de um movimento pertence à coluna de cabeçalho mais próxima (débito, crédito ou
saldo). Depois **verifica pelo saldo**: saldo atual − saldo anterior = movimento com
sinal, testando as duas ordens possíveis (cronológica ou inversa). Se as colunas e o
saldo discordarem, o saldo ganha. Num PDF com uma só coluna de valores, se o banco
escreve "-" nas saídas e nunca "+", um valor sem sinal é uma entrada.

### 2. Dar nome ao comerciante (`catalogo.py` + `chave_comerciante()`)
A mesma subscrição aparece com descrições diferentes todos os meses:
`COMPRA 4521 NETFLIX.COM 866-579 12/03` e `COMPRA 8812 NETFLIX.COM 866-579 12/04`.
- Primeiro tenta o **catálogo** de comerciantes conhecidos. As palavras-chave contam
  como **palavras inteiras** e a mais comprida ganha: "HOMEOPATIA" não é MEO,
  "LOJA DAS PRENDAS" não é renda e "MEO ENERGIA" ganha a "MEO". Há também uma lista de
  nomes que *parecem* subscrições mas não são: abastecer na Galp ou na Repsol (a conta
  da luz vem como `GALP ENERGIA` ou por débito direto), `GOOGLE PLAY`, `GYMSHARK`...
- Numa **transferência para uma pessoa** (`MB WAY PARA ...`), palavras genéricas como
  SEGURO ou RENDA podem ser um apelido, por isso não contam.
- Se não estiver no catálogo, cria uma **chave**: tira acentos, pontuação, tudo o que
  tenha números (referências, datas, nº de cartão) e palavras de ruído bancário
  (COMPRA, DD, TRF, MB WAY, Cobrança SDD, Trf Imediata Sepa+...), e fica com as 2
  primeiras palavras.
- **Débitos diretos** (SDD) são quase sempre contas fixas, por isso precisam de menos
  provas, tal como os comerciantes do catálogo. **MB WAY para pessoas** precisa de mais
  um pagamento, porque valores redondos (10 €, 20 €) repetem-se por acaso.
- **Poupança e investimento** (cofres, cripto, PPR, corretoras) são recorrentes mas não
  são custos: aparecem à parte e não entram no "Pagas por mês". O mesmo para o dinheiro
  que **só muda de conta** (ver o ponto 5).

### 3. Detetar recorrência (`recorrentes.py`)
Para cada comerciante:
1. Junta os pagamentos do mesmo dia e ordena por data.
2. Calcula os **intervalos em dias** entre pagamentos seguidos.
3. Compara a **mediana** dos intervalos com as periodicidades conhecidas
   (7, 30.4, 61, 91, 182, 365 dias, cada uma com uma tolerância).
4. Exige **regularidade**: ≥70% dos intervalos dentro da tolerância.
5. Exige **valor estável**: coeficiente de variação (desvio-padrão / mediana) ≤ 15%.
   Exceções: categorias de consumo (luz, água) podem variar, e uma subida de preço
   não elimina a subscrição (desde que seja uma subida, de no máximo +60%, e haja
   provas suficientes do preço antigo).
6. Comerciantes conhecidos precisam de 2 pagamentos; desconhecidos precisam de 3
   (menos provas para quem já sabemos que vende subscrições).

Porquê a **mediana** e não a média? Porque é robusta a outliers: um mês em que o
pagamento atrasou 10 dias não estraga a estimativa do intervalo.

### 4. Alertas
- **Subida de preço**: procura, do mais recente para trás, o ponto que divide os
  pagamentos em dois blocos estáveis com preços diferentes ("antes" e "depois") e
  compara as **medianas**. Assim o alerta diz *quando* subiu e não dispara por causa de
  um mês estranho. Serviços cobrados em dólares oscilam com o câmbio, por isso só há
  alerta se o preço não for fixo ao cêntimo e subir pelo menos 10%.
- **Possivelmente cancelada**: não houve pagamento há mais de 1,5× o intervalo normal.
  Estas não entram nos totais.
- **Cobrança duplicada**: num serviço mensal, dois pagamentos com menos de 10 dias.

### 5. Dinheiro que só muda de conta (`entre_contas.py`)
Carregar a Revolut com 100 € todos os meses tem o padrão perfeito de uma subscrição, mas
não é um custo. Estes movimentos vão para o bloco "Entre contas tuas" de três formas:
- **Carregamentos de contas digitais** (Revolut, N26, Wise, Moey!...), pelo catálogo. Os
  planos pagos (`REVOLUT PREMIUM`) têm chaves mais compridas e continuam a ser custos, e
  `REVOLUTION FITNESS` não é a Revolut.
- **Transferências com o nome do titular** (`TRF P/ TIAGO RODRIGUES`), se a pessoa escrever
  o nome em *Corrigir → Contas tuas*. Exige o primeiro nome e um apelido (o banco às vezes
  corta: `RODRIGU`): `MB WAY PARA TIAGO` pode ser um amigo e `TRF DE MARIA RODRIGUES` pode
  ser a mãe.
- **Pares entre extratos de contas diferentes**: sai X de uma conta e entra exatamente X
  noutra, entre 1 dia antes e 3 dias depois, e pelo menos um dos lados parece uma
  transferência. Só conta entre ficheiros que se sobrepõem no tempo (contas diferentes):
  ficheiros do mesmo banco mês a mês não fazem pares.

### 6. Pagamentos anuais ("A confirmar")
Um seguro ou o Amazon Prime pagos uma vez por ano aparecem uma só vez no extrato, por isso
nunca se provam pelo padrão, e antes desapareciam do talão. Agora, num extrato longo, os
pagamentos únicos a um comerciante do catálogo ou por débito direto vão para
**"A confirmar"**: "só 1 pagamento em 4 meses: se for anual, renova por volta de 06/2027
(4,16 € por mês)". Se o pagamento foi há menos de 40 dias, pode ser uma subscrição nova.
Os consumos (luz, água) ficam de fora. Nada disto entra no total até a pessoa confirmar em
*Corrigir → Adicionar*, onde escolhe a frequência; lá também se acrescenta à mão o que falta.

### 7. Contas divididas (`partilhas.py`)
Se pagas a MEO (40 €) e os dois colegas de casa te mandam 10 € cada, o teu custo real é
20 €. O talão mostra a conta inteira, as **partes pagas por outros** e o total já com o
desconto.
1. Entradas de **pessoas** ("MB WAY DE ANA COSTA", "TRF DE ...", "Payment from ..."). Não
   contam empresas, rendimentos (salário, bolsa), as tuas próprias transferências e, se
   escreveres o teu nome, pessoas com o teu apelido (mais provável serem família).
2. Para cada conta fixa, cada pagamento da conta procura uma entrada dessa pessoa até
   **7 dias** antes ou depois. A pessoa acompanha a conta se aparecer em **≥60%** dos meses
   em que lá esteve (há quem se atrase ou falhe um mês) e quase sempre com a **mesma
   fração** da conta. A fração (e não o valor) é o que conta: numa conta de luz o valor
   muda todos os meses, a metade não. Uma pessoa paga no máximo 60% de uma conta.
3. Se a pessoa encaixa em várias contas, ganha primeiro uma conta que se costuma dividir
   (casa, internet, luz, streaming); depois a que fecha uma **divisão em partes iguais**
   com as outras pessoas (duas pessoas com 1/3 cada, mais tu), e só depois a mais próxima
   no tempo. As frações de todos nunca passam a conta inteira.
4. Em *Corrigir → Dividir* desliga-se uma parte detetada ou divide-se uma conta à mão
   (ex.: a luz por 3).

### 8. Confiança
`0,5 × regularidade + 0,3 × estabilidade do valor + 0,2 × (está no catálogo)`.
É uma heurística simples e explicável, e um ponto de partida para um modelo treinado
com dados rotulados (ver [Próximos passos](#próximos-passos)).

### 9. Supermercado (`supermercados.py`)
O extrato diz onde se comprou e quanto, mas não o quê. Por isso a página mostra o que dá
para saber com ele: o gasto por mês e por cadeia, quantas idas, o valor médio de cada ida e
quanto somam as **idas pequenas** (abaixo de 10 €, ajustável). As cadeias são reconhecidas
pela descrição (Continente, Pingo Doce, Lidl, Mercadona, Aldi, Auchan, Intermarché,
Minipreço…); as bombas de gasolina das cadeias ficam de fora e as devoluções descontam. As
médias usam o período todo do extrato, e o gráfico só mostra os meses completos.

**Mudar de cadeia compensa?** Para isso usa-se o índice anual de preços dos supermercados
online da [DECO PROteste](https://www.deco.proteste.pt/familia-consumo/supermercado/noticias/supermercado-online-lidera-ranking-precos-baixos)
(`dados/precos_supermercados.csv`; em 2025, Continente = 100 e Minipreço = 104):
`poupança = gasto na cadeia × (1 − índice da mais barata ÷ índice da cadeia)`. O Lidl, o
Aldi e o Mercadona não entram no estudo. No exemplo, mudar de cadeia poupava 0,60 € por mês,
e a app responde isso mesmo: "Quase nada".

Os extratos carregam-se uma vez, em Contas fixas, e ficam na sessão (`ui/extratos.py`): o
Streamlit esquece o que um widget tinha quando se muda de página, por isso os ficheiros são
guardados à parte e a página do supermercado usa o extrato já lido.

### 10. Luz (`energia.py`)
`custo = termo fixo (€/dia) × dias + preço (€/kWh) × consumo (kWh)`, convertido para
um mês médio de 30,4 dias. Comparamos antes de IVA e taxas porque essas são
praticamente iguais em todas as comercializadoras e não mudam o ranking.
A leitura do PDF usa `pdfplumber` + expressões regulares. Cada comercializadora tem o
seu layout, por isso é "melhor esforço": a app mostra o que leu e deixa corrigir.

## Avaliação

`python -m avaliacao.avaliar --n 1000` gera 1000 extratos e compara o resultado da app
com a resposta certa. Cada extrato é de uma pessoa diferente: 4 a 11 subscrições
escolhidas de 32 tipos (streaming, telecomunicações, luz, água, ginásio, seguros, renda,
propinas, e 5 serviços **fora do catálogo** que só podem ser encontrados pelo padrão),
escritas como em bancos diferentes, com o dia de cobrança a variar e débitos que passam
para segunda-feira quando calham ao fim de semana. O ruído é o de um mês normal
(supermercado, cafés, Uber) e os casos que enganavam a versão anterior.

Os três casos da vida real são gerados à parte, com outro gerador aleatório, para os
extratos de antes ficarem iguais: carregamentos da Revolut/Wise/N26 e transferências para
outra conta no nome do titular (35% e 20% das pessoas), um pagamento anual que só cabe uma
vez no extrato (35%), uma compra avulsa numa loja do catálogo (30%), uma conta dividida
com 1 a 3 colegas que às vezes se atrasam ou falham um mês (45%) e, para baralhar, a mesada
dos pais com o apelido do titular perto do dia da renda. Com `--sem-nome` a avaliação faz
de conta que a pessoa não escreveu o nome.

**Como se conta.** Cada linha do talão é comparada com os rótulos dos movimentos que a
formam: é um acerto se a maioria pertence a uma subscrição verdadeira. Precisão =
acertos / linhas mostradas; recall = acertos / subscrições verdadeiras.

**O erro que sobra** (quase todos os falsos positivos) é um corte de cabelo a preço fixo
de 4 em 4 ou de 5 em 5 semanas: tem exatamente o padrão de uma subscrição, mas não é
uma. Não foi "corrigido" com mais uma regra feita à medida dos dados de avaliação, o que
seria sobreajuste. É o tipo de caso que um modelo treinado com dados reais deve
resolver (ver abaixo).

O `tests/test_avaliacao.py` corre uma versão pequena (60 extratos) a cada alteração e
falha se a precisão descer de 95% ou o recall de 97%.

## Limitações

- **Os números acima vêm de dados sintéticos.** Medem se as regras fazem o que devem
  nos casos previstos; extratos reais vão ter casos que ninguém previu. O próximo passo
  é rotular extratos reais (ver abaixo).
- **As ofertas de luz são de exemplo** (comercializadoras fictícias), e a app avisa
  disso. A leitura da fatura e as contas são reais; para comparar com preços atuais
  pode carregar-se uma tabela própria.
- A leitura de faturas de luz é "melhor esforço": cada comercializadora tem o seu layout.
- **No supermercado, o extrato não diz o que se comprou**, por isso não dá para saber se o
  mesmo carrinho ficava mais barato noutra cadeia. O índice da DECO é a média de um cabaz de
  mais de 200 produtos, com preços online, e não inclui o Lidl, o Aldi nem o Mercadona.
  Uma compra no El Corte Inglés fica de fora, porque não se distingue o supermercado do resto
  da loja. O passo seguinte é ler as faturas eletrónicas (Continente, Lidl Plus), que têm os
  produtos.
- **Sem o nome do titular**, uma transferência para outra conta tua conta como custo, e uma
  mesada da família perto do dia da renda pode passar por uma parte da renda. A app mostra
  quem "paga parte" de cada conta para se poder desligar.
- **"A confirmar" não sabe distinguir** um pagamento anual de uma compra avulsa na mesma
  loja (um jogo na PlayStation Store). Por isso não entra no total sem confirmação.
- Nas contas divididas, os dados sintéticos têm divisões em partes iguais e colegas
  com nomes de pessoas. Na vida real há divisões desiguais, uma só transferência para
  várias contas e partes pagas em dinheiro; nesses casos divide-se à mão.

## Próximos passos

1. **Dados reais de ofertas de luz** com atualização mensal automática.
2. **Telecomunicações**: ler faturas da MEO/NOS/Vodafone/DIGI e comparar pacotes.
3. **Modelo de ML para a deteção**: recolher rótulos reais ("é / não é subscrição")
   de utilizadores voluntários e treinar um classificador (ex.: gradient boosting) com
   features como regularidade, variação do valor, nº de pagamentos, tipo de pagamento
   (cartão, débito direto, MB WAY), categoria e palavras da descrição. Comparar com a
   heurística atual usando a mesma avaliação.
4. **Alertas por email** quando aparece uma oferta mais barata (conta de utilizador).
5. **Ligação direta ao banco** via Open Banking (PSD2) em vez de CSV — exige parceiro
   licenciado; só vale a pena depois de validar que as pessoas usam.

## Licença

[MIT](LICENSE). Os tipos de letra têm a sua própria licença (OFL), em `static/fontes`.
