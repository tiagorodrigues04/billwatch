# 👀 BillWatch

**Descobre quanto pagas todos os meses e onde estás a pagar a mais.**

Carregas o extrato do banco e a app encontra sozinha as subscrições e contas fixas
(Netflix, ginásio, MEO, renda...), diz-te quanto isso dá por mês e por ano e avisa-te
quando um preço sobe, quando há uma cobrança duplicada ou quando um serviço parou de
ser cobrado. Também lê a fatura da luz em PDF e compara-a com outras ofertas.

Inspirado no Rocket Money (EUA), adaptado a bancos e serviços portugueses.

---

## Como correr

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
streamlit run app.py               # abre em http://localhost:8501
pytest                             # ~100 testes
```

A app arranca com um **extrato de exemplo** (12 meses fictícios de um estudante), por
isso dá para experimentar logo sem dados reais. Os testes correm sozinhos no GitHub a
cada alteração (separador *Actions*).

## Formatos de extrato suportados

| Tipo | O que a app percebe |
|---|---|
| **CSV** | separador `;` `,` tab ou `\|` · codificação UTF-8 ou Windows · linhas de título antes da tabela · vários blocos no mesmo ficheiro (ex.: Revolut: resumo + conta + cripto) |
| **Excel** | `.xlsx`, `.xls` antigo e `.xls` que na verdade é HTML · datas reais ou em número série · títulos antes da tabela |
| **PDF** | com grelha ou só texto · colunas Débito/Crédito, "Dinheiro retirado/recebido", "Money out/in" ou um só "Montante" · do mais antigo para o mais recente ou ao contrário · várias secções e páginas · descrições em 2 linhas · data só na 1.ª linha de cada dia · PDFs com letras estragadas (`(cid:231)`) |
| **Valores** | `1.234,56` `1,234.56` `-9,99` `9,99-` `(9,99)` `+9,99` `9,99 D/C` `€9.99` `9,99 €` `1 234,56` · ou valor positivo com coluna D/C |
| **Datas** | `05-10-2026` `05/10/26` `05.10.2026` `2026-10-05` `5 out 2026` `5 de out. de 2026` `Oct 5, 2026` · e sem ano (`05.10`), com o ano tirado do período do extrato |
| **Limpeza** | movimentos revertidos/recusados saem · só a moeda principal (EUR) · linhas de saldo inicial/final e totais saem · ficheiros repetidos ou sobrepostos não duplicam |

**Se um formato não for reconhecido**, a app não fica presa: mostra a tabela e pede ao
utilizador que diga que coluna é a data, a descrição e o valor (já com um palpite
feito pelo conteúdo). Há também a opção *Inverter sinais*, e um **diagnóstico anónimo**
(letras → `x`, números → `9`) que se pode partilhar para corrigir o leitor sem expor dados.

Está tudo testado em `tests/formatos/`: 17 extratos fictícios que imitam formas reais de
exportar, todos gerados a partir dos mesmos movimentos — e o teste exige que todos deem
**exatamente** os mesmos movimentos, comerciantes e resultado final.
Para acrescentar um formato novo: imitá-lo em `tests/gerar_formatos.py` e correr
`python tests/gerar_formatos.py`.

## Estrutura

```
app.py                  Interface (Streamlit): abas Subscrições, Luz, Como funciona
contas/
  texto.py              Ler números e datas escritos de qualquer forma; anonimizar
  extrato.py            CSV/Excel/HTML → tabela → (data, descricao, valor); nome do comerciante
  leitor_pdf.py         Extratos em PDF (tabelas desenhadas ou palavras com posição)
  catalogo.py           Comerciantes conhecidos em PT → nome e categoria
  recorrentes.py        O algoritmo de deteção de pagamentos recorrentes + alertas
  energia.py            Lê a fatura da luz (PDF) e compara ofertas
  exemplo.py            Gera o extrato fictício usado na demo e nos testes
dados/
  ofertas_luz.csv       Tabela de ofertas — VALORES DE EXEMPLO, substituir por reais
  fatura_exemplo.pdf    Fatura fictícia para testar a leitura de PDF
tests/
  test_contas.py        Testes do algoritmo e casos concretos
  test_formatos.py      Os 17 formatos + ficheiros estragados, PDFs protegidos/digitalizados
  gerar_formatos.py     Gera a coleção de formatos fictícios
  formatos/             Os ficheiros gerados + resultados esperados
.github/workflows/      Corre os testes no GitHub a cada alteração
```

## Como funciona (o que tens de saber explicar numa entrevista)

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
- Primeiro tenta o **catálogo** de comerciantes conhecidos (palavras-chave curtas como
  `MEO` ou `NOS` só contam como palavra inteira, para "HOMEOPATIA" não virar MEO).
- Se não estiver no catálogo, cria uma **chave**: tira acentos, pontuação, tudo o que
  tenha números (referências, datas, nº de cartão) e palavras de ruído bancário
  (COMPRA, DD, TRF, MB WAY, Cobrança SDD, Trf Imediata Sepa+...), e fica com as 2
  primeiras palavras.
- **Débitos diretos** (SDD) são quase sempre contas fixas, por isso precisam de menos
  provas, tal como os comerciantes do catálogo.
- **Poupança e investimento** (cofres, cripto, PPR, corretoras) são recorrentes mas não
  são custos: aparecem à parte e não entram no "Pagas por mês".

### 3. Detetar recorrência (`recorrentes.py`)
Para cada comerciante:
1. Junta os pagamentos do mesmo dia e ordena por data.
2. Calcula os **intervalos em dias** entre pagamentos seguidos.
3. Compara a **mediana** dos intervalos com as periodicidades conhecidas
   (7, 30.4, 61, 91, 182, 365 dias, cada uma com uma tolerância).
4. Exige **regularidade**: ≥70% dos intervalos dentro da tolerância.
5. Exige **valor estável**: coeficiente de variação (desvio-padrão / mediana) ≤ 15%.
   Exceções: categorias de consumo (luz, água) podem variar, e uma subida de preço
   isolada não elimina a subscrição.
6. Comerciantes conhecidos precisam de 2 pagamentos; desconhecidos precisam de 3
   (menos provas para quem já sabemos que vende subscrições).

Porquê a **mediana** e não a média? Porque é robusta a outliers: um mês em que o
pagamento atrasou 10 dias não estraga a estimativa do intervalo.

### 4. Alertas
- **Subida de preço**: anda para trás desde o último pagamento enquanto o valor for
  igual; o valor anterior a esse bloco é o preço antigo. Assim o alerta diz *quando*
  subiu, não só que subiu.
- **Possivelmente cancelada**: não houve pagamento há mais de 1,5× o intervalo normal.
  Estas não entram nos totais.
- **Cobrança duplicada**: num serviço mensal, dois pagamentos com menos de 10 dias.

### 5. Confiança
`0,5 × regularidade + 0,3 × estabilidade do valor + 0,2 × (está no catálogo)`.
É uma heurística simples e explicável — um bom ponto de partida para substituir por
um modelo treinado quando tiveres dados rotulados (ver Próximos passos).

### 6. Luz (`energia.py`)
`custo = termo fixo (€/dia) × dias + preço (€/kWh) × consumo (kWh)`, convertido para
um mês médio de 30,4 dias. Comparamos antes de IVA e taxas porque essas são
praticamente iguais em todas as comercializadoras e não mudam o ranking.
A leitura do PDF usa `pdfplumber` + expressões regulares. Cada comercializadora tem o
seu layout, por isso é "melhor esforço": a app mostra o que leu e deixa corrigir.

## ⚠️ Antes de mostrar a alguém

- **`dados/ofertas_luz.csv` tem preços inventados** e comercializadoras fictícias.
  Substitui por ofertas reais e atuais (simulador da ERSE/Poupa Energia, ou os sites
  das comercializadoras) e põe a data de atualização na app.
- Testa com extratos reais de vários bancos (CGD, Millennium, Santander, Novo Banco,
  BPI, Revolut, Moey...) — de certeza que algum formato vai partir o leitor. Cada um
  que corrigires é um teste novo.
- Testa com faturas reais de luz de várias comercializadoras.

## Publicar de graça (link para o CV)

1. Cria um repositório no GitHub e faz push desta pasta.
2. Vai a **share.streamlit.io**, entra com o GitHub e escolhe o repositório e `app.py`.
3. Em poucos minutos tens um link público tipo `billwatch.streamlit.app`.

## Próximos passos (roadmap)

1. **Dados reais de ofertas de luz** com atualização mensal automática.
2. **Telecomunicações**: ler faturas da MEO/NOS/Vodafone/DIGI e comparar pacotes.
3. **Modelo de ML para a deteção**: pede a 20 colegas para marcarem "é / não é
   subscrição" nos resultados, e treina um classificador (ex.: gradient boosting)
   com features como regularidade, variação do valor, nº de pagamentos, categoria e
   palavras da descrição. Compara com a heurística atual (precisão/recall) — isto é
   ouro para o CV de Ciência de Dados.
4. **Alertas por email** quando aparece uma oferta mais barata (conta de utilizador).
5. **Ligação direta ao banco** via Open Banking (PSD2) em vez de CSV — exige parceiro
   licenciado; só vale a pena depois de validar que as pessoas usam.
