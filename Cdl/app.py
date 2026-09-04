# -*- coding: utf-8 -*-
"""
App de cálculo de Capacitância de Dupla Camada (Cdl / ECSA)
Reproduz a lógica do script Origin (Cdl_Dyo.ogs) em Python + Streamlit.

Como rodar:
    pip install -r requirements.txt
    streamlit run app.py
"""

import io
import hashlib
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm

st.set_page_config(page_title="Cálculo de Cdl (ECSA)", layout="wide")

# ----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ----------------------------------------------------------------------------

def ler_arquivo(uploaded_file):
    """Lê um arquivo (csv/txt/xlsx) tentando detectar separador e decimal."""
    nome = uploaded_file.name
    if nome.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
        return df

    raw = uploaded_file.read()
    uploaded_file.seek(0)
    texto = raw.decode("utf-8", errors="ignore")

    # tenta separador automático primeiro (vírgula, ponto e vírgula, tab)
    for sep in [None, ";", ",", "\t"]:
        try:
            df = pd.read_csv(io.StringIO(texto), sep=sep, engine="python")
            # se só formou 1 coluna, provavelmente o separador está errado
            if df.shape[1] > 1:
                # checa se as colunas numéricas vieram como texto (decimal vírgula)
                amostra = df.select_dtypes(include="object")
                if not amostra.empty:
                    try:
                        df2 = pd.read_csv(io.StringIO(texto), sep=sep, engine="python", decimal=",")
                        if df2.shape[1] > 1:
                            return df2
                    except Exception:
                        pass
                return df
        except Exception:
            continue

    raise ValueError(f"Não foi possível ler o arquivo {nome}. Verifique o formato.")


def detectar_colunas(df):
    """Encontra as colunas de Potencial (E) e Corrente (I) priorizando 'WE(1)'."""
    cols = list(df.columns)

    def achar(padroes_prioritarios, padrao_generico):
        candidatos_prioritarios = [
            c for c in cols
            if all(p in str(c).lower() for p in padroes_prioritarios)
        ]
        if candidatos_prioritarios:
            return candidatos_prioritarios[0]
        candidatos_genericos = [c for c in cols if padrao_generico in str(c).lower()]
        if candidatos_genericos:
            return candidatos_genericos[0]
        return None

    col_e = achar(["we(1)", "potential"], "potential")
    col_i = achar(["we(1)", "current"], "current")
    return col_e, col_i


def detectar_coluna_scan(df):
    """Tenta encontrar uma coluna que identifique o número do scan/ciclo."""
    for c in df.columns:
        cl = str(c).lower()
        # "Segment" normalmente identifica apenas um ramo (ida ou volta), não
        # um ciclo completo; filtrá-lo eliminaria Ia ou Ic.
        if "cycle" in cl or "scan" in cl:
            return c
    return None


def extrair_ultimo_scan(df, col_scan=None, n_scans_esperado=3,
                        col_potencial=None):
    """
    Retorna apenas os dados do último scan/ciclo do arquivo.

    - Se col_scan for informada (ou detectada automaticamente), filtra pelas
      linhas cujo valor nessa coluna é o maior (último ciclo).
    - Caso não exista coluna de scan, identifica as inversões da direção do
      potencial e usa o último ciclo completo entre três retornos consecutivos.
    - A divisão em partes iguais é apenas o último recurso.
    """
    if col_scan is not None and col_scan in df.columns:
        serie = df[col_scan]
        try:
            valores = pd.to_numeric(serie, errors="coerce")
            ultimo = valores.max()
            df_ultimo = df[valores == ultimo].reset_index(drop=True)
        except Exception:
            valores_unicos = sorted(serie.dropna().unique())
            ultimo = valores_unicos[-1]
            df_ultimo = df[serie == ultimo].reset_index(drop=True)
        info = f"Último scan identificado pela coluna '{col_scan}' (valor = {ultimo})."
        return df_ultimo, info

    n = len(df)

    if col_potencial is not None and col_potencial in df.columns:
        potencial = pd.to_numeric(df[col_potencial], errors="coerce").to_numpy()
        diferencas = np.diff(potencial)
        escala = np.nanmax(potencial) - np.nanmin(potencial)
        passos_finitos = np.abs(diferencas[np.isfinite(diferencas)])
        passos_finitos = passos_finitos[passos_finitos > 0]
        passo_tipico = float(np.median(passos_finitos)) if len(passos_finitos) else 0.0
        tolerancia = max(float(escala) * 1e-9, 1e-12)
        tolerancia_extremo = max(1.5 * passo_tipico, float(escala) * 0.005)
        potencial_minimo = float(np.nanmin(potencial))
        potencial_maximo = float(np.nanmax(potencial))

        # Ignora passos nulos/repetidos e localiza mudanças reais de sentido.
        indices_validos = np.flatnonzero(
            np.isfinite(diferencas) & (np.abs(diferencas) > tolerancia)
        )
        retornos_tipados = []
        if len(indices_validos) >= 2:
            direcao_anterior = np.sign(diferencas[indices_validos[0]])
            for indice_diferenca in indices_validos[1:]:
                direcao_atual = np.sign(diferencas[indice_diferenca])
                if direcao_atual != direcao_anterior:
                    # diff[i] liga os pontos i e i+1; ao mudar o sinal, i é o
                    # possível retorno. Só aceitamos retornos próximos de um
                    # extremo global, descartando oscilações no meio do ramo.
                    valor_retorno = potencial[indice_diferenca]
                    tipo = None
                    if abs(valor_retorno - potencial_maximo) <= tolerancia_extremo:
                        tipo = "max"
                    elif abs(valor_retorno - potencial_minimo) <= tolerancia_extremo:
                        tipo = "min"

                    if tipo is not None:
                        retorno = (int(indice_diferenca), tipo)
                        if retornos_tipados and retornos_tipados[-1][1] == tipo:
                            # Vários pequenos retornos perto do mesmo vértice
                            # representam um único extremo; fica o mais recente.
                            retornos_tipados[-1] = retorno
                        else:
                            retornos_tipados.append(retorno)
                    direcao_anterior = direcao_atual

        retornos = [indice for indice, _ in retornos_tipados]
        if len(retornos) >= 3:
            inicio = retornos[-3]
            fim = retornos[-1]
            df_ultimo = df.iloc[inicio:fim + 1].reset_index(drop=True)
            info = (
                "Último scan identificado pelas inversões do potencial "
                f"(linhas {inicio} a {fim})."
            )
            return df_ultimo, info

    n_scans_esperado = max(1, int(n_scans_esperado))
    tamanho = n // n_scans_esperado
    if tamanho == 0:
        return df, "Não foi possível dividir o arquivo em scans; usando o arquivo completo."
    inicio = tamanho * (n_scans_esperado - 1)
    df_ultimo = df.iloc[inicio:].reset_index(drop=True)
    info = (f"Coluna de scan não encontrada/selecionada; arquivo dividido em "
            f"{n_scans_esperado} partes iguais e usada a última "
            f"(linhas {inicio} a {n - 1}).")
    return df_ultimo, info




def calcular_potencial_extracao(x):
    """
    Calcula automaticamente o potencial de extração (ponto médio da janela de
    potencial) usando a fórmula:
        (ponto_mais_alto - ponto_mais_baixo) / 2 + ponto_mais_baixo
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return np.nan, np.nan, np.nan
    ponto_mais_alto = np.max(x)
    ponto_mais_baixo = np.min(x)
    potencial = (ponto_mais_alto - ponto_mais_baixo) / 2.0 + ponto_mais_baixo
    return potencial, ponto_mais_alto, ponto_mais_baixo


def interpolar_ia_ic(x, y, target_x):
    """
    Extrai as duas correntes no potencial central da janela.

    Quando há um ponto medido exatamente no potencial alvo, usa sua corrente.
    Caso contrário, calcula a corrente por interpolação linear entre os dois
    pontos consecutivos que envolvem o alvo, em cada passagem do voltamograma.
    São consideradas as duas passagens da curva pelo potencial central. Entre
    as duas correntes obtidas nesse mesmo potencial, a maior é a anódica (Ia) e
    a menor é a catódica (Ic). Pontos medidos têm prioridade; a interpolação é
    usada apenas quando o potencial central não foi medido em uma passagem.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) != len(y) or not np.isfinite(target_x):
        return np.nan, np.nan

    exatas = []
    interpoladas = []

    # Primeiro procura amostras realmente medidas no potencial central.
    for indice, (potencial, corrente) in enumerate(zip(x, y)):
        if not np.all(np.isfinite([potencial, corrente])):
            continue
        if np.isclose(potencial, target_x, rtol=0.0, atol=1e-12):
            exatas.append((indice, float(corrente)))

    # Em seguida calcula as alternativas interpoladas, uma para cada passagem.
    for j in range(len(x) - 1):
        xa, xb = x[j], x[j + 1]
        ya, yb = y[j], y[j + 1]
        if not np.all(np.isfinite([xa, xb, ya, yb])):
            continue

        # Extremos estritos impedem que um ponto exato também seja interpolado.
        if min(xa, xb) < target_x < max(xa, xb) and not np.isclose(xa, xb):
            fracao = (target_x - xa) / (xb - xa)
            interpoladas.append((j + fracao, float(ya + fracao * (yb - ya))))

    # Alguns equipamentos encerram o ciclo uma fração de passo antes do
    # potencial inicial. Se apenas uma passagem envolveu estritamente o centro,
    # completa a outra pela reta dos dois últimos pontos (ou, como alternativa,
    # dos dois primeiros), limitada a no máximo dois passos de potencial.
    if len(exatas) + len(interpoladas) < 2 and len(x) >= 2:
        intervalos_borda = [(len(x) - 2, len(x) - 1), (0, 1)]
        for ia_borda, ib_borda in intervalos_borda:
            xa, xb = x[ia_borda], x[ib_borda]
            ya, yb = y[ia_borda], y[ib_borda]
            if not np.all(np.isfinite([xa, xb, ya, yb])) or np.isclose(xa, xb):
                continue
            distancia = min(abs(target_x - xa), abs(target_x - xb))
            if distancia <= 2.0 * abs(xb - xa):
                fracao = (target_x - xa) / (xb - xa)
                corrente = float(ya + fracao * (yb - ya))
                interpoladas.append((ia_borda + fracao, corrente))
                break

    # Cada item representa uma passagem da curva pelo potencial central. Se há
    # dois pontos experimentais, nenhuma interpolação é necessária. Havendo só
    # um, completa-se a segunda passagem com o cruzamento interpolado.
    if len(exatas) >= 2:
        correntes = [corrente for _, corrente in exatas[-2:]]
    elif len(exatas) == 1:
        indice_exato, corrente_exata = exatas[0]
        alternativas = [
            (posicao, corrente)
            for posicao, corrente in interpoladas
            if abs(posicao - indice_exato) > 1.0
        ]
        correntes = [corrente_exata]
        if alternativas:
            correntes.append(alternativas[-1][1])
    else:
        correntes = [corrente for _, corrente in interpoladas[-2:]]

    if len(correntes) < 2:
        return np.nan, np.nan

    return float(max(correntes)), float(min(correntes))


def regressao_pearson(x, y):
    """Regressão linear e Pearson, ignorando pares inválidos."""
    x = np.array(x, dtype=float)
    y = np.array(y, dtype=float)
    validos = np.isfinite(x) & np.isfinite(y)
    x = x[validos]
    y = y[validos]
    if len(x) < 2 or np.allclose(x, x[0]):
        return np.nan, np.nan, np.nan, np.nan
    slope, intercept = np.polyfit(x, y, 1)
    r = np.corrcoef(x, y)[0, 1]
    return intercept, slope, r, r ** 2


def fmt_livre(v):
    """Formata número sem casas decimais fixas (ex.: 2.0, 1.25, 0.125...)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    s = f"{v:.6g}"
    return s


def gerar_cores(paleta, n, cores_customizadas=None):
    """Gera uma lista de `n` cores a partir de uma paleta do matplotlib,
    ou retorna as cores customizadas escolhidas pelo usuário."""
    if paleta == "custom":
        return cores_customizadas
    cmap = plt.get_cmap(paleta)
    if n <= 1:
        return [cmap(0.5)]
    return [cmap(i / (n - 1)) for i in range(n)]


def controles_limites_eixos(container, prefixo, valores_x, valores_y):
    """Cria controles opcionais para limites manuais dos eixos."""
    automatico = container.checkbox(
        "Escala automática dos eixos",
        value=True,
        key=f"{prefixo}_escala_automatica",
    )
    if automatico:
        return None

    x = np.asarray(valores_x, dtype=float)
    y = np.asarray(valores_y, dtype=float)
    x = x[np.isfinite(x)]
    y = y[np.isfinite(y)]
    x_min, x_max = (float(np.min(x)), float(np.max(x))) if len(x) else (0.0, 1.0)
    y_min, y_max = (float(np.min(y)), float(np.max(y))) if len(y) else (0.0, 1.0)

    limite_x_min = container.number_input("X mínimo", value=x_min, format="%.6g", key=f"{prefixo}_xmin")
    limite_x_max = container.number_input("X máximo", value=x_max, format="%.6g", key=f"{prefixo}_xmax")
    limite_y_min = container.number_input("Y mínimo", value=y_min, format="%.6g", key=f"{prefixo}_ymin")
    limite_y_max = container.number_input("Y máximo", value=y_max, format="%.6g", key=f"{prefixo}_ymax")
    return limite_x_min, limite_x_max, limite_y_min, limite_y_max


def aplicar_limites_eixos(ax, limites):
    """Aplica limites manuais somente quando os intervalos são válidos."""
    if limites is None:
        return
    x_min, x_max, y_min, y_max = limites
    if x_min < x_max:
        ax.set_xlim(x_min, x_max)
    if y_min < y_max:
        ax.set_ylim(y_min, y_max)


def imagem_grafico(fig, formato):
    """Retorna o gráfico em memória para download em PNG ou JPEG."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format=formato.lower(), dpi=300, bbox_inches="tight")
    buffer.seek(0)
    return buffer.getvalue()


POSICOES_LEGENDA = {
    "Automática": "best",
    "Superior esquerda": "upper left",
    "Superior centro": "upper center",
    "Superior direita": "upper right",
    "Centro esquerda": "center left",
    "Centro": "center",
    "Centro direita": "center right",
    "Inferior esquerda": "lower left",
    "Inferior centro": "lower center",
    "Inferior direita": "lower right",
}


# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
# INTERFACE
# ----------------------------------------------------------------------------

st.title("⚡ Cálculo de Capacitância de Dupla Camada (Cdl / ECSA)")
st.caption("Versão do cálculo: 2026-09-04.2 — resultados sem cache de correntes")

# ============================================================================
# TELA INICIAL: carregamento dos arquivos
# ============================================================================

st.header("📂 Carregar arquivos")
st.write("Selecione os arquivos de voltametria — um arquivo para cada velocidade de varredura.")

arquivos = st.file_uploader(
    "Arquivos de voltametria",
    type=["csv", "txt", "xlsx", "xls"],
    accept_multiple_files=True,
)

if not arquivos:
    st.info("👆 Envie os arquivos acima para liberar as etapas de análise.")
    st.stop()

st.caption(
    "Arquivos recebidos nesta execução: "
    + " | ".join(
        f"{arq.name}: {arq.size} bytes, ID {hashlib.sha256(arq.getvalue()).hexdigest()[:8]}"
        for arq in arquivos
    )
)

# ============================================================================
# PROCESSAMENTO DOS ARQUIVOS
# ============================================================================
# Essa parte continua com a mesma lógica do código original.
# Os resultados ficam disponíveis para todas as abas.

configs = []

with st.sidebar:
    st.subheader("Configuração única das medidas")

    # pega colunas do primeiro arquivo como referência
    try:
        primeiro_df = ler_arquivo(arquivos[0])
        colunas_ref = list(primeiro_df.columns)
        col_e_detectada, col_i_detectada = detectar_colunas(primeiro_df)
    except Exception:
        colunas_ref = []
        col_e_detectada, col_i_detectada = None, None

    st.markdown("As colunas de potencial e corrente são detectadas em cada arquivo.")

    escolha_scan_global = st.selectbox(
        "Coluna que identifica o scan/ciclo (ou Automático)",
        ["Automático"] + colunas_ref,
        index=0,
        key="scan_col_global",
    )

    n_scans_global = st.number_input(
        "Nº de scans no arquivo (usado se não houver coluna)",
        min_value=1,
        value=3,
        step=1,
        key="n_scans_global",
    )

    capacitancia_especifica = st.number_input(
        "Capacitância específica (mF/cm²)",
        min_value=0.000001,
        value=0.04,
        step=0.01,
        format="%.6f",
        key="capacitancia_especifica",
    )

    # processa todos os arquivos com a configuração única
    for indice_arquivo, arq in enumerate(arquivos):
        try:
            df_completo = ler_arquivo(arq)
        except Exception as e:
            st.error(f"{arq.name}: {e}")
            continue

        col_e_arquivo, col_i_arquivo = detectar_colunas(df_completo)
        if col_e_arquivo is None or col_i_arquivo is None:
            st.error(
                f"{arq.name}: não foi possível identificar as colunas "
                "WE(1).Potential e WE(1).Current."
            )
            continue

        # determina coluna de scan a usar
        col_scan_auto = detectar_coluna_scan(df_completo)
        col_scan_usar = None
        if escolha_scan_global != "Automático":
            col_scan_usar = escolha_scan_global
        elif col_scan_auto is not None:
            col_scan_usar = col_scan_auto

        df_ultimo, info_scan = extrair_ultimo_scan(
            df_completo,
            col_scan_usar,
            n_scans_global,
            col_potencial=col_e_arquivo,
        )

        # Centro e correntes são determinados somente no último scan deste
        # arquivo, agora delimitado pelos pontos de retorno do potencial.
        x_tab = np.array([], dtype=float)
        y_tab = np.array([], dtype=float)
        pot_extracao = np.nan
        pot_central_calculado = np.nan
        pot_alto = np.nan
        pot_baixo = np.nan
        try:
            x_tab = df_ultimo[col_e_arquivo].astype(float).to_numpy()
            y_tab = df_ultimo[col_i_arquivo].astype(float).to_numpy() * 1000.0

            x_analise = x_tab
            y_analise = y_tab
            pot_central_calculado, pot_alto, pot_baixo = calcular_potencial_extracao(
                x_analise
            )
            pot_extracao = pot_central_calculado
        except Exception:
            pass

        # Ia, Ic e média
        try:
            ia_tab, ic_tab = interpolar_ia_ic(
                x_analise, y_analise, pot_extracao
            )

            i_media_tab = np.nanmean(
                [
                    abs(ia_tab) if not np.isnan(ia_tab) else np.nan,
                    abs(ic_tab) if not np.isnan(ic_tab) else np.nan,
                ]
            )

        except Exception:
            ia_tab, ic_tab, i_media_tab = np.nan, np.nan, np.nan

        configs.append(
            {
                "nome": arq.name,
                "id_arquivo": f"{arq.name}_{arq.size}_{indice_arquivo}",
                "df": df_ultimo,
                "col_e": col_e_arquivo,
                "col_i": col_i_arquivo,
                "vel": np.nan,
                "pot_extracao": pot_extracao,
                "pot_central_calculado": pot_central_calculado,
                "pot_maximo": pot_alto,
                "pot_minimo": pot_baixo,
                "info_scan": info_scan,
                "x": x_tab,
                "y_mA": y_tab,
                "ia": ia_tab,
                "ic": ic_tab,
                "i_media": i_media_tab,
            }
        )

# ============================================================================
# VELOCIDADES DE VARREDURA
# ============================================================================

st.header("⚡ Informar velocidades de varredura")
st.write(
    "Informe a velocidade correspondente a cada arquivo. O step de potencial "
    "não permite calcular a velocidade sem o tempo de aquisição."
)

with st.form("form_velocidades"):
    velocidades_informadas = []
    for cfg in configs:
        velocidade = st.number_input(
            f"{cfg['nome']} — velocidade de varredura (mV/s)",
            min_value=0.0,
            value=None,
            step=1.0,
            format="%.6g",
            key=f"velocidade_varredura_{cfg['id_arquivo']}",
            placeholder="Obrigatório",
        )
        velocidades_informadas.append(velocidade)

    velocidades_confirmadas = st.form_submit_button(
        "Confirmar velocidades e analisar",
        type="primary",
    )

assinatura_arquivos = tuple((arq.name, arq.size) for arq in arquivos)
valores_velocidade_validos = (
    len(configs) == len(arquivos)
    and all(v is not None and np.isfinite(v) and v > 0 for v in velocidades_informadas)
)

if velocidades_confirmadas and valores_velocidade_validos:
    st.session_state["velocidades_confirmadas_para"] = assinatura_arquivos

velocidades_validas = (
    valores_velocidade_validos
    and st.session_state.get("velocidades_confirmadas_para") == assinatura_arquivos
)

if not velocidades_validas:
    st.session_state["calculado"] = False
    if velocidades_confirmadas:
        st.error("Informe uma velocidade maior que zero para cada arquivo antes de continuar.")
    else:
        st.info("Preencha e confirme todas as velocidades para liberar a análise.")
    st.stop()

for cfg, velocidade in zip(configs, velocidades_informadas):
    cfg["vel"] = float(velocidade)

# ============================================================================
# ABAS
# ============================================================================

tab_resultados, tab_graficos = st.tabs(
    ["📊 Dados e resultados", "📈 Gráficos"]
)

# ============================================================================
# CÁLCULO
# ============================================================================

if True:  # cálculo automático a cada alteração dos arquivos ou parâmetros

    calculado = False
    resultados = []
    curvas = []

    for cfg in configs:
        if (not np.isfinite(cfg["vel"]) or cfg["vel"] <= 0
                or not np.isfinite(cfg["pot_extracao"])):
            continue

        # O potencial e as duas correntes já foram determinados isoladamente
        # durante o processamento do arquivo. Esta etapa apenas reúne os
        # resultados individuais para tabelas, regressões e gráficos.
        x = cfg["x"]
        y_mA = cfg["y_mA"]
        target_x = cfg["pot_extracao"]
        ia = cfg["ia"]
        ic = cfg["ic"]

        curvas.append(
            {
                "nome": cfg["nome"],
                "vel": cfg["vel"],
                "x": x,
                "y": y_mA,
                "pot_extracao": target_x,
                "ia": ia,
                "ic": ic,
            }
        )

        i_media = cfg["i_media"]

        resultados.append(
            {
                "arquivo": cfg["nome"],
                "scan_rate_mV_s": cfg["vel"],
                "scan_rate_V_s": cfg["vel"] / 1000.0,
                "Ia_mA": ia,
                "Ic_mA": ic,
                "I_media_mA": i_media,
            }
        )

    if len(resultados) < 2:
        st.warning(
            "São necessários pelo menos 2 arquivos com scan rate > 0 para a regressão linear."
        )
        calculado = False
    else:
        df_res = pd.DataFrame(resultados).sort_values("scan_rate_V_s").reset_index(drop=True)

        x_v = df_res["scan_rate_V_s"].to_numpy()
        y_ia = df_res["Ia_mA"].to_numpy()
        y_ic = df_res["Ic_mA"].to_numpy()
        y_media = df_res["I_media_mA"].to_numpy()

        if np.any(np.isnan(y_ia)) or np.any(np.isnan(y_ic)):
            st.warning(
                "Alguns pontos anódicos ou catódicos não foram encontrados no potencial usado para extração das correntes."
            )

        int_a, slope_a, r_a, r2_a = regressao_pearson(x_v, y_ia)
        int_c, slope_c, r_c, r2_c = regressao_pearson(x_v, y_ic)
        r_c_abs = abs(r_c)

        int_m, slope_m, r_m, r2_m = regressao_pearson(x_v, y_media)

        pot_medio_geral = float(
            np.nanmean([c["pot_extracao"] for c in curvas if c.get("pot_extracao") is not None])
        )

        reg = dict(
            int_a=int_a,
            slope_a=slope_a,
            r_a=r_a,
            r2_a=r2_a,
            int_c=int_c,
            slope_c=slope_c,
            r_c=r_c_abs,
            r2_c=r2_c,
            int_m=int_m,
            slope_m=slope_m,
            r_m=r_m,
            r2_m=r2_m,
        )
        calculado = True


# ============================================================================
# GRÁFICOS
# ============================================================================

with tab_graficos:

    if not calculado:
        st.info("Adicione ao menos dois arquivos válidos para gerar os gráficos automaticamente.")
    else:
        int_a, slope_a, r_a, r2_a = (
            reg["int_a"], reg["slope_a"], reg["r_a"], reg["r2_a"]
        )
        int_c, slope_c, r_c_abs, r2_c = (
            reg["int_c"], reg["slope_c"], reg["r_c"], reg["r2_c"]
        )

        st.subheader("4.1 Voltammograms — last scan from each file")
        graf_cv, op_cv = st.columns([1.6, 1.0], vertical_alignment="top")
        editor_cv = op_cv.popover("✏️ Editar gráfico 4.1", use_container_width=True)
        cv_titulo = editor_cv.text_input("Título", "Overlaid voltammograms", key="cv_titulo_en")
        cv_eixo_x = editor_cv.text_input("Eixo X", "Potential (V)", key="cv_eixo_x_en")
        cv_eixo_y = editor_cv.text_input("Eixo Y", "Current (mA)", key="cv_eixo_y_en")
        # A legenda vem diretamente da velocidade confirmada para cada arquivo.
        # Não usamos estado editável aqui, pois ele mantinha textos antigos após
        # uma alteração de velocidade ou da ordem dos uploads.
        labels_curvas = [f"{curva['vel']:.6g} mV/s" for curva in curvas]
        posicao_legenda_cv = editor_cv.selectbox(
            "Posição da legenda",
            list(POSICOES_LEGENDA.keys()),
            index=2,
            key="posicao_legenda_cv",
        )

        paletas_disponiveis = {
            "Tab10 (padrão, cores bem distintas)": "tab10",
            "Set2 (pastel)": "Set2",
            "Set1": "Set1",
            "Viridis": "viridis",
            "Plasma": "plasma",
            "Cividis": "cividis",
            "Cool": "cool",
            "Rainbow": "rainbow",
            "Turbo": "turbo",
            "Personalizado (escolher cor de cada curva)": "custom",
        }

        nome_paleta = editor_cv.selectbox(
            "Paleta de cores",
            list(paletas_disponiveis.keys()),
            index=0,
        )
        paleta_key = paletas_disponiveis[nome_paleta]

        cores_customizadas = None

        if paleta_key == "custom":
            editor_cv.caption("Escolha uma cor para cada curva:")
            cores_customizadas = []
            cores_padrao_mpl = plt.rcParams["axes.prop_cycle"].by_key()["color"]

            for idx, curva in enumerate(curvas):
                cor_default = cores_padrao_mpl[idx % len(cores_padrao_mpl)]

                if not isinstance(cor_default, str):
                    cor_default = "#{:02x}{:02x}{:02x}".format(
                        int(cor_default[0] * 255),
                        int(cor_default[1] * 255),
                        int(cor_default[2] * 255),
                    )

                cor = editor_cv.color_picker(
                    curva["nome"], value=cor_default, key=f"cor_{idx}"
                )

                cores_customizadas.append(cor)

        cores = gerar_cores(paleta_key, len(curvas), cores_customizadas)
        x_cv_todos = np.concatenate([np.asarray(curva["x"], dtype=float) for curva in curvas])
        y_cv_todos = np.concatenate([np.asarray(curva["y"], dtype=float) for curva in curvas])
        mostrar_linha_potencial = editor_cv.checkbox(
            "Mostrar linha do potencial central",
            value=True,
            key="mostrar_linha_potencial",
        )
        limites_cv = controles_limites_eixos(editor_cv, "cv", x_cv_todos, y_cv_todos)
        formato_cv = op_cv.selectbox("Formato da imagem", ["PNG", "JPEG"], key="formato_cv")

        fig_cv, ax_cv = plt.subplots(figsize=(4.6, 3.1), dpi=180)

        for curva, cor, label_curva in zip(curvas, cores, labels_curvas):
            ax_cv.plot(
                curva["x"],
                curva["y"],
                color=cor,
                linewidth=1.5,
                label=label_curva,
            )

        y_cv_finitos = y_cv_todos[np.isfinite(y_cv_todos)]
        if mostrar_linha_potencial and len(y_cv_finitos):
            ax_cv.vlines(
                pot_medio_geral,
                float(np.min(y_cv_finitos)),
                float(np.max(y_cv_finitos)),
                color="black",
                linestyle="--",
                linewidth=1,
            )
        ax_cv.set_xlabel(cv_eixo_x)
        ax_cv.set_ylabel(cv_eixo_y)
        ax_cv.set_title(cv_titulo)
        ymin_cv, ymax_cv = ax_cv.get_ylim()
        ax_cv.set_ylim(ymin_cv, ymax_cv + 0.30 * (ymax_cv - ymin_cv))
        aplicar_limites_eixos(ax_cv, limites_cv)
        ax_cv.legend(
            fontsize=7,
            loc=POSICOES_LEGENDA[posicao_legenda_cv],
            ncol=min(3, max(1, len(curvas))),
            frameon=False,
        )
        fig_cv.tight_layout()
        graf_cv.pyplot(fig_cv, width="content", dpi=300)
        op_cv.download_button(
            f"Baixar gráfico 4.1 ({formato_cv})",
            data=imagem_grafico(fig_cv, formato_cv),
            file_name=f"grafico_4_1.{formato_cv.lower().replace('jpeg', 'jpg')}",
            mime="image/png" if formato_cv == "PNG" else "image/jpeg",
            use_container_width=True,
        )

        # Gráfico Ia vs scan rate
        st.subheader("4.2 Ia vs. scan rate")
        graf_ia, op_ia = st.columns([1.6, 1.0], vertical_alignment="top")
        editor_ia = op_ia.popover("✏️ Editar gráfico 4.2", use_container_width=True)
        ia_titulo = editor_ia.text_input("Título", "Ia vs. scan rate", key="ia_titulo_en")
        ia_eixo_x = editor_ia.text_input("Eixo X", "Scan rate (mV/s)", key="ia_eixo_x_en")
        eixo_ia = editor_ia.text_input("Eixo Y", "Ia (mA)", key="eixo_ia_en")
        legenda_ia = editor_ia.text_input("Legenda da curva", "Ia (anodic)", key="legenda_ia_en")
        posicao_legenda_ia = editor_ia.selectbox(
            "Posição da legenda",
            list(POSICOES_LEGENDA.keys()),
            index=3,
            key="posicao_legenda_ia",
        )
        cor_ia = editor_ia.color_picker("Cor da curva", "#d62728", key="cor_ia")
        x_mV = x_v * 1000.0
        xx_mV = np.linspace(min(x_mV), max(x_mV), 50)
        limites_ia = controles_limites_eixos(editor_ia, "ia", x_mV, y_ia)
        formato_ia = op_ia.selectbox("Formato da imagem", ["PNG", "JPEG"], key="formato_ia")
        fig_ia, ax_ia = plt.subplots(figsize=(4.4, 2.9), dpi=180)
        ax_ia.scatter(x_mV, y_ia, color=cor_ia, label=legenda_ia)
        ax_ia.plot(
            xx_mV,
            slope_a * (xx_mV / 1000.0) + int_a,
            color=cor_ia,
            linestyle="--",
            label="Linear fit",
        )
        ax_ia.set_xlabel(ia_eixo_x)
        ax_ia.set_ylabel(eixo_ia)
        ax_ia.set_title(ia_titulo)
        texto_ia = f"slope = {fmt_livre(slope_a)} mF\nR² = {fmt_livre(r2_a)}"
        ymin_ia, ymax_ia = ax_ia.get_ylim()
        ax_ia.set_ylim(ymin_ia, ymax_ia + 0.35 * (ymax_ia - ymin_ia))
        aplicar_limites_eixos(ax_ia, limites_ia)
        ax_ia.text(0.03, 0.96, texto_ia, transform=ax_ia.transAxes, fontsize=8, va="top")
        ax_ia.legend(loc=POSICOES_LEGENDA[posicao_legenda_ia], fontsize=8, frameon=False)
        fig_ia.tight_layout()
        graf_ia.pyplot(fig_ia, width="content", dpi=300)
        op_ia.download_button(
            f"Baixar gráfico 4.2 ({formato_ia})",
            data=imagem_grafico(fig_ia, formato_ia),
            file_name=f"grafico_4_2.{formato_ia.lower().replace('jpeg', 'jpg')}",
            mime="image/png" if formato_ia == "PNG" else "image/jpeg",
            use_container_width=True,
        )

        # Gráfico Ic vs scan rate
        st.subheader("4.3 Ic vs. scan rate")
        graf_ic, op_ic = st.columns([1.6, 1.0], vertical_alignment="top")
        editor_ic = op_ic.popover("✏️ Editar gráfico 4.3", use_container_width=True)
        ic_titulo = editor_ic.text_input("Título", "Ic vs. scan rate", key="ic_titulo_en")
        ic_eixo_x = editor_ic.text_input("Eixo X", "Scan rate (mV/s)", key="ic_eixo_x_en")
        eixo_ic = editor_ic.text_input("Eixo Y", "Ic (mA)", key="eixo_ic_en")
        legenda_ic = editor_ic.text_input("Legenda da curva", "Ic (cathodic)", key="legenda_ic_en")
        posicao_legenda_ic = editor_ic.selectbox(
            "Posição da legenda",
            list(POSICOES_LEGENDA.keys()),
            index=3,
            key="posicao_legenda_ic",
        )
        cor_ic = editor_ic.color_picker("Cor da curva", "#1f77b4", key="cor_ic")
        limites_ic = controles_limites_eixos(editor_ic, "ic", x_mV, y_ic)
        formato_ic = op_ic.selectbox("Formato da imagem", ["PNG", "JPEG"], key="formato_ic")
        fig_ic, ax_ic = plt.subplots(figsize=(4.4, 2.9), dpi=180)
        ax_ic.scatter(x_mV, y_ic, color=cor_ic, label=legenda_ic)
        ax_ic.plot(
            xx_mV,
            slope_c * (xx_mV / 1000.0) + int_c,
            color=cor_ic,
            linestyle="--",
            label="Linear fit",
        )
        ax_ic.set_xlabel(ic_eixo_x)
        ax_ic.set_ylabel(eixo_ic)
        ax_ic.set_title(ic_titulo)
        texto_ic = f"slope = {fmt_livre(slope_c)} mF\nR² = {fmt_livre(r2_c)}"
        ymin_ic, ymax_ic = ax_ic.get_ylim()
        ax_ic.set_ylim(ymin_ic, ymax_ic + 0.35 * (ymax_ic - ymin_ic))
        aplicar_limites_eixos(ax_ic, limites_ic)
        ax_ic.text(0.03, 0.96, texto_ic, transform=ax_ic.transAxes, fontsize=8, va="top")
        ax_ic.legend(loc=POSICOES_LEGENDA[posicao_legenda_ic], fontsize=8, frameon=False)
        fig_ic.tight_layout()
        graf_ic.pyplot(fig_ic, width="content", dpi=300)
        op_ic.download_button(
            f"Baixar gráfico 4.3 ({formato_ic})",
            data=imagem_grafico(fig_ic, formato_ic),
            file_name=f"grafico_4_3.{formato_ic.lower().replace('jpeg', 'jpg')}",
            mime="image/png" if formato_ic == "PNG" else "image/jpeg",
            use_container_width=True,
        )

        # Gráfico combinado Ia e Ic
        st.subheader("4.4 Ia and Ic — comparison")
        graf_comb, op_comb = st.columns([1.6, 1.0], vertical_alignment="top")
        editor_comb = op_comb.popover("✏️ Editar gráfico 4.4", use_container_width=True)
        comb_titulo = editor_comb.text_input(
            "Título", "Ia and Ic vs. scan rate — comparison", key="comb_titulo_en"
        )
        comb_eixo_x = editor_comb.text_input(
            "Eixo X", "Scan rate (mV/s)", key="comb_eixo_x_en"
        )
        eixo_comb = editor_comb.text_input("Eixo Y", "Current (mA)", key="eixo_comb_en")
        legenda_comb_ia = editor_comb.text_input("Legenda de Ia", "Ia (anodic)", key="legenda_comb_ia_en")
        legenda_comb_ic = editor_comb.text_input("Legenda de Ic", "Ic (cathodic)", key="legenda_comb_ic_en")
        posicao_legenda_comb = editor_comb.selectbox(
            "Posição da legenda",
            ["Entre as curvas"] + list(POSICOES_LEGENDA.keys()),
            index=0,
            key="posicao_legenda_comb",
        )
        cor_comb_ia = editor_comb.color_picker("Cor de Ia", "#d62728", key="cor_comb_ia")
        cor_comb_ic = editor_comb.color_picker("Cor de Ic", "#1f77b4", key="cor_comb_ic")
        limites_comb = controles_limites_eixos(
            editor_comb,
            "comb",
            np.concatenate([x_mV, x_mV]),
            np.concatenate([y_ia, y_ic]),
        )
        formato_comb = op_comb.selectbox("Formato da imagem", ["PNG", "JPEG"], key="formato_comb")
        fig_comb, ax_comb = plt.subplots(figsize=(4.4, 2.9), dpi=180)
        ax_comb.scatter(x_mV, y_ia, color=cor_comb_ia, label=legenda_comb_ia)
        ax_comb.plot(
            xx_mV,
            slope_a * (xx_mV / 1000.0) + int_a,
            color=cor_comb_ia,
            linestyle="--",
            label="Linear fit Ia",
        )
        ax_comb.scatter(x_mV, y_ic, color=cor_comb_ic, label=legenda_comb_ic)
        ax_comb.plot(
            xx_mV,
            slope_c * (xx_mV / 1000.0) + int_c,
            color=cor_comb_ic,
            linestyle="--",
            label="Linear fit Ic",
        )
        ax_comb.set_xlabel(comb_eixo_x)
        ax_comb.set_ylabel(eixo_comb)
        ax_comb.set_title(comb_titulo)
        texto_comb = (
            f"Ia\n"
            f"slope = {fmt_livre(slope_a)} mF\n"
            f"R² = {fmt_livre(r2_a)}\n"
            f"Ic\n"
            f"slope = {fmt_livre(slope_c)} mF\n"
            f"R² = {fmt_livre(r2_c)}"
        )
        ymin_comb, ymax_comb = ax_comb.get_ylim()
        ax_comb.set_ylim(ymin_comb, ymax_comb + 0.15 * (ymax_comb - ymin_comb))
        aplicar_limites_eixos(ax_comb, limites_comb)

        # Coloca o bloco Ia/Ic entre as duas regressões, no lado esquerdo.
        x_texto = float(np.min(x_mV) + 0.25 * (np.max(x_mV) - np.min(x_mV)))
        y_anodica_texto = slope_a * (x_texto / 1000.0) + int_a
        y_catodica_texto = slope_c * (x_texto / 1000.0) + int_c
        y_texto = float((y_anodica_texto + y_catodica_texto) / 2.0)
        ax_comb.text(
            x_texto,
            y_texto,
            texto_comb,
            transform=ax_comb.transData,
            fontsize=6,
            ha="center",
            va="center",
            linespacing=1.0,
        )

        # Posiciona a legenda no espaço central entre as regressões anódica e
        # catódica, acompanhando automaticamente a geometria dos dados.
        x_legenda = float(np.min(x_mV) + 0.82 * (np.max(x_mV) - np.min(x_mV)))
        y_anodica_legenda = slope_a * (x_legenda / 1000.0) + int_a
        y_catodica_legenda = slope_c * (x_legenda / 1000.0) + int_c
        y_legenda = float((y_anodica_legenda + y_catodica_legenda) / 2.0)
        opcoes_legenda_comb = dict(
            fontsize=5.5,
            frameon=False,
            handlelength=1.8,
            labelspacing=0.15,
            ncol=1,
        )
        if posicao_legenda_comb == "Entre as curvas":
            ax_comb.legend(
                loc="center",
                bbox_to_anchor=(x_legenda, y_legenda),
                bbox_transform=ax_comb.transData,
                **opcoes_legenda_comb,
            )
        else:
            ax_comb.legend(
                loc=POSICOES_LEGENDA[posicao_legenda_comb],
                **opcoes_legenda_comb,
            )
        fig_comb.tight_layout()
        graf_comb.pyplot(fig_comb, width="content", dpi=300)
        op_comb.download_button(
            f"Baixar gráfico 4.4 ({formato_comb})",
            data=imagem_grafico(fig_comb, formato_comb),
            file_name=f"grafico_4_4.{formato_comb.lower().replace('jpeg', 'jpg')}",
            mime="image/png" if formato_comb == "PNG" else "image/jpeg",
            use_container_width=True,
        )

# ============================================================================
# RESULTADOS
# ============================================================================

with tab_resultados:

    if not calculado:
        st.info("Adicione ao menos dois arquivos válidos para gerar os resultados automaticamente.")
    else:
        slope_a, r2_a = reg["slope_a"], reg["r2_a"]
        slope_c, r2_c = reg["slope_c"], reg["r2_c"]

        st.subheader("Resultados")

        df_res_exibicao = df_res.drop(
            columns=["scan_rate_V_s", "I_media_mA"],
            errors="ignore",
        ).rename(
            columns={
                "arquivo": "Arquivo",
                "scan_rate_mV_s": "Velocidade de varredura (mV/s)",
                "Ia_mA": "Corrente anódica, Ia (mA)",
                "Ic_mA": "Corrente catódica, Ic (mA)",
            }
        )

        df_regressao = pd.DataFrame(
            {
                "Ramo": ["Anódico", "Catódico"],
                "Slope / Cdl (mF)": [slope_a, slope_c],
                "R²": [r2_a, r2_c],
                "Cs (mF/cm²)": [capacitancia_especifica, capacitancia_especifica],
                "ECSA (cm²)": [
                    abs(slope_a) / capacitancia_especifica,
                    abs(slope_c) / capacitancia_especifica,
                ],
            }
        )

        st.markdown("**Dados das medidas**")
        st.dataframe(
            df_res_exibicao,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("**Regressão linear e ECSA**")
        st.dataframe(
            df_regressao,
            use_container_width=True,
            hide_index=True,
        )

        # Somente a exportação une as duas tabelas lado a lado, mantendo cada
        # informação em uma coluna própria para importação no Origin.
        df_resultados_completos = pd.concat(
            [
                df_res_exibicao.reset_index(drop=True),
                df_regressao.reset_index(drop=True),
            ],
            axis=1,
        )

        # Exportação
        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_resultados_completos.to_excel(
                writer,
                sheet_name="Resultados_ECSA",
                index=False,
            )

        buffer.seek(0)

        texto_resultados = df_resultados_completos.to_csv(
            index=False,
            sep="\t",
            decimal=",",
        )

        col_excel, col_txt = st.columns(2)
        with col_excel:
            st.download_button(
                "⬇️ Baixar resultados (Excel)",
                data=buffer,
                file_name="Resultados_ECSA.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with col_txt:
            st.download_button(
                "⬇️ Baixar resultados (TXT)",
                data=texto_resultados.encode("utf-8-sig"),
                file_name="Resultados_ECSA.txt",
                mime="text/plain",
                use_container_width=True,
            )
