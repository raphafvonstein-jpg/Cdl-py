# LSV e impedância — Python + Streamlit

Aplicativo para organizar até três curvas por amostra, associar cada LSV à sua impedância e comparar resultados. Esta publicação inclui **somente LSV**, sem integração com Origin e sem incorporar o aplicativo Cdl.

## Rodar no computador

Use Python 3.12. Na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Em Linux/macOS, use `.venv/bin/python` no lugar de `.\.venv\Scripts\python.exe`.

O Streamlit informa o endereço local, normalmente `http://localhost:8501`. O ponto de entrada é **`app.py` na raiz**.

## GitHub e Streamlit Community Cloud

1. Extraia `dist/lsv-streamlit.zip` ou envie os arquivos Python deste projeto ao seu repositório GitHub.
2. Mantenha `app.py`, `requirements.txt`, `README.md`, a pasta `lsv_app` e `.streamlit/config.toml` na estrutura original. `tests` e `examples` também podem ser publicados.
3. Acesse https://share.streamlit.io/ e escolha **Create app**.
4. Selecione seu repositório e branch; informe **`app.py`** como arquivo principal.
5. Nas configurações avançadas, escolha **Python 3.12** e publique.

Não envie `.venv`, `venv`, sessões pessoais, arquivos de medições, diretórios de validação nem segredos. O pacote gerado contém somente código, testes e um exemplo sintético. O `.gitignore` deixa a versão HTML antiga na pasta local `LSV/`, fora do código desta migração. A pasta `Cdl` existente não é importada pelo aplicativo nem incluída no ZIP.

Documentação oficial: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

### Estrutura

```text
app.py
requirements.txt
lsv_app/
  core.py       # leitura e cálculos
  ui.py         # interface e estado por usuário
  plots.py      # curvas, Nyquist e barras
  export.py     # XLSX, CSV e ZIP
.streamlit/config.toml
tests/
examples/sessao_exemplo.json
```

## Usar o aplicativo

- **Amostras:** dê nomes às amostras, adicione até três LSV de uma vez ou um a um e associe a impedância de cada eletrodo. Os seletores de potencial/corrente usam os cabeçalhos do arquivo. Informe as áreas geométrica e eletroativa em cm². As entradas LSV são sempre **V e A**.
- **Tratamento:** selecione a referência, pH, Eref vs SHE, temperatura e Eeq. Se os dados já estiverem em RHE, não se aplica deslocamento adicional. Os nomes não são substituídos automaticamente: campos vazios ou duplicados exibem aviso e preservam o texto digitado.
- **Planilhas:** selecione a amostra. As abas são LSV 1, LSV 2, Média e DP, LSV 3. A aba de médias tem somente seis colunas: potencial comum, duas médias, dois DP e n. Baixe XLSX ou prepare um ZIP com todas as amostras.
- **Gráficos:** escolha curvas individuais ou médias, os eixos e a normalização. A comparação aceita duplicatas e triplicatas. O Nyquist usa Z′ e −Z″ com aspecto igual. O gráfico de barras permite selecionar 10, 50 e 100 mA/cm², com média, DP e valores escritos. É possível baixar PNG, SVG e CSV.
- **Sessão:** abra ou salve o JSON pela barra lateral. Sessões da versão HTML v2–v9 são reconhecidas e migradas quando necessário.

Para experimentar sem dados pessoais, abra `examples/sessao_exemplo.json` em **Abrir sessão JSON**. O exemplo é inteiramente sintético.

## Equações e critérios

| Coluna | Grandeza | Equação |
|---|---|---|
| A | Potencial medido vs referência usada | Entrada em V |
| B | Potencial vs RHE | A + Eref(vs SHE) + ln(10) RT/F × pH |
| C | Queda iR | G × Rs |
| D | Potencial corrigido vs RHE | B − C |
| E | Sobrepotencial em V | D − Eeq |
| F | Sobrepotencial em mV | E × 1000 |
| G | Corrente em A | Entrada em A |
| H | Corrente em mA | G × 1000 |
| I | Densidade geométrica | H / área geométrica |
| J | Densidade eletroativa | H / área eletroativa |

T é usado em kelvin. Eref depende do eletrodo, do eletrólito/concentração e da temperatura usados; não se presume um valor tabelado apenas pelo nome. Para dados já em RHE, B = A. Fonte: https://pubs.acs.org/doi/10.1021/acsenergylett.5c01269

Rs é a coordenada Z′ do **primeiro ponto com −Z″ positivo**, na ordem do arquivo, sem extrapolação ou ajuste de circuito. Zim/Im(Z)/Z″ é convertido para −Z″; um cabeçalho já negativo é preservado. Não se aplica valor absoluto aos dados.

As réplicas são interpoladas em 201 potenciais **medidos** comuns antes de calcular as médias e o DP amostral (n−1). Oscilações geradas pela correção iR não são confundidas com inversões da aquisição. Uma inversão real ou potencial medido repetido bloqueia a média; curvas individuais válidas continuam disponíveis.

O ponto de 10 mA/cm² nas curvas é localizado na curva média geométrica, com o potencial/sobrepotencial escrito. Nas barras, primeiro se obtém o sobrepotencial de cada eletrodo em 10/50/100 e depois sua média/DP. Não se extrapola e não se excluem réplicas indisponíveis para formar uma média parcial. Uma réplica gera valor individual sem DP. Fonte do indicador geométrico: https://authors.library.caltech.edu/records/9hdcw-5f261

Os XLSX contêm fórmulas com resultados numéricos em cache, parâmetros rastreáveis e apenas as quatro abas solicitadas. Após editar entradas no Excel, os resultados dependem do recálculo pelo editor; gerar novamente no aplicativo recompõe todas as estatísticas.

## Dados e sessões

No Streamlit, os arquivos são enviados ao servidor que executa o aplicativo e ficam no estado da sessão do usuário. O código não os grava em disco e não usa cache global de medições. Fechar/recarregar a conexão pode perder os dados: baixe o JSON para continuar depois. Sessões de usuários diferentes não compartilham os dados carregados.

## Testar e empacotar

```powershell
python -m unittest discover -s tests -v
python build_release.py
```

Os testes incluem cálculos, conversão, normalizações, estatística, migração JSON, fórmulas e valores em cache no XLSX, ZIP e testes do aplicativo com `streamlit.testing.v1.AppTest`.
