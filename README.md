# 💶 Contas à Vista

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
pip install -r requirements.txt
streamlit run app.py               # abre em http://localhost:8501
pytest                             # 19 testes
```

A app arranca com um **extrato de exemplo** (12 meses fictícios de um estudante), por
isso dá para experimentar logo sem dados reais.

## Estrutura

```
app.py                 Interface (Streamlit): abas Subscrições, Luz, Como funciona
contas/
  extrato.py           Lê CSVs de qualquer banco e normaliza para (data, descricao, valor)
  catalogo.py          Comerciantes conhecidos em PT → nome e categoria
  recorrentes.py       O algoritmo de deteção de pagamentos recorrentes + alertas
  energia.py           Lê a fatura da luz (PDF) e compara ofertas
  exemplo.py           Gera o extrato fictício usado na demo e nos testes
dados/
  ofertas_luz.csv      Tabela de ofertas — VALORES DE EXEMPLO, substituir por reais
  fatura_exemplo.pdf   Fatura fictícia para testar a leitura de PDF
tests/test_contas.py   Testes automáticos
```

## Como funciona (o que tens de saber explicar numa entrevista)

### 1. Ler o extrato (`extrato.py`)
Cada banco exporta de forma diferente: `;` ou `,`, `1.234,56` ou `1234.56`, uma
coluna "Montante" com sinal ou duas colunas "Débito"/"Crédito", linhas de cabeçalho
com o IBAN antes da tabela. O módulo:
- procura a linha onde começa a tabela (a primeira que tem "data" e "valor/débito");
- experimenta separadores e codificações (`utf-8`, `latin-1`);
- encontra as colunas pelo nome (cuidado: "Data Valor" é uma data, não um valor!);
- converte números no formato português com `converter_numero()`.

### 2. Dar nome ao comerciante (`catalogo.py` + `chave_comerciante()`)
A mesma subscrição aparece com descrições diferentes todos os meses:
`COMPRA 4521 NETFLIX.COM 866-579 12/03` e `COMPRA 8812 NETFLIX.COM 866-579 12/04`.
- Primeiro tenta o **catálogo** de comerciantes conhecidos (palavras-chave curtas como
  `MEO` ou `NOS` só contam como palavra inteira, para "HOMEOPATIA" não virar MEO).
- Se não estiver no catálogo, cria uma **chave**: tira acentos, pontuação, tudo o que
  tenha números (referências, datas, nº de cartão) e palavras de ruído bancário
  (COMPRA, DD, TRF, MB WAY...), e fica com as 2 primeiras palavras.

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
3. Em poucos minutos tens um link público tipo `contas-a-vista.streamlit.app`.

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
