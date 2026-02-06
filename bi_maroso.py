import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="BI Logística | Maroso",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. CSS HACKING ---
def local_css():
    st.markdown("""
        <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 5rem;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        div[data-testid="metric-container"] {
            background-color: #262730;
            border: 1px solid #4c4c4c;
            padding: 10px;
            border-radius: 8px;
            box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
        }
        div[data-testid="metric-container"]:hover {
            border-color: #ff4b4b;
        }
        .big-font {
            font-size: 24px !important;
            font-weight: bold;
            color: #ececec;
            margin-bottom: 20px;
        }
        </style>
    """, unsafe_allow_html=True)

local_css()

# --- 3. CARREGAMENTO DE DADOS ---
@st.cache_data
def load_data():
    try:
        # Lê o CSV exportado (Ajuste o caminho se necessário)
        df = pd.read_csv("2026-02-06T12-02_export.csv")
        df['data'] = pd.to_datetime(df['data']).dt.tz_localize(None)
        df = df.sort_values('data')
        # FILTRA "OUTROS" LOGO NA CARGA
        df = df[df['Tipo'] != 'OUTROS']
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()

df_raw = load_data()

# --- 4. BARRA LATERAL (FILTROS GLOBAIS) ---
with st.sidebar:
    st.header("🎛️ Filtros de Análise")
    
    if not df_raw.empty:
        min_date = df_raw['data'].min().date()
        max_date = df_raw['data'].max().date()
        
        data_range = st.date_input(
            "Período",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
        
        tipos_disponiveis = sorted(df_raw['Tipo'].unique())
        tipos_selecionados = st.multiselect(
            "Tipo de Veículo", 
            tipos_disponiveis, 
            default=tipos_disponiveis
        )
    else:
        st.warning("Sem dados carregados.")
        st.stop()

# --- 5. LÓGICA DE FILTRAGEM ---
# 1. Aplica filtros da Sidebar primeiro
mask = df_raw['Tipo'].isin(tipos_selecionados)
if len(data_range) == 2:
    mask = mask & (df_raw['data'].dt.date >= data_range[0]) & (df_raw['data'].dt.date <= data_range[1])

df_filtered = df_raw[mask].copy()

# --- 6. CABEÇALHO ---
c1, c2 = st.columns([3, 1])
c1.markdown('<p class="big-font">Dashboard de Ociosidade da Frota</p>', unsafe_allow_html=True)
if len(data_range) == 2:
    c2.caption(f"📅 {data_range[0].strftime('%d/%m')} até {data_range[1].strftime('%d/%m')}")

if df_filtered.empty:
    st.warning("⚠️ Nenhum dado para exibir com os filtros atuais.")
    st.stop()

# --- 7. GRÁFICOS INTERATIVOS ---
g1, g2 = st.columns([2, 1])

# --- GRÁFICO DE BARRAS (COM INTERATIVIDADE E TODOS OS DIAS) ---
with g1:
    st.subheader("Evolução Diária")
    
    df_bar = df_filtered.groupby(['data', 'Tipo'])['Qtd'].sum().reset_index()
    
    # ========================================================================
    # 🎯 CORREÇÃO: GARANTIR QUE TODOS OS DIAS APAREÇAM NO EIXO X
    # ========================================================================
    # 1. Cria range completo de datas do período filtrado
    if len(data_range) == 2:
        todas_datas = pd.date_range(start=data_range[0], end=data_range[1], freq='D')
    else:
        todas_datas = pd.date_range(start=df_filtered['data'].min(), end=df_filtered['data'].max(), freq='D')
    
    # 2. Cria um DataFrame com todas as combinações Data x Tipo
    tipos_existentes = df_filtered['Tipo'].unique()
    grid_completo = pd.DataFrame([
        {'data': d, 'Tipo': t} for d in todas_datas for t in tipos_existentes
    ])
    
    # 3. Faz MERGE com os dados reais (preenchendo vazios com 0)
    df_bar_completo = grid_completo.merge(df_bar, on=['data', 'Tipo'], how='left')
    df_bar_completo['Qtd'] = df_bar_completo['Qtd'].fillna(0)
    # ========================================================================
    
    # Criação do Gráfico
    fig_bar = px.bar(
        df_bar_completo, 
        x='data', 
        y='Qtd', 
        color='Tipo',
        color_discrete_map={'BITRUCK': '#0083b8', 'CARRETA': "#8a3131"},
        text='Qtd',
        title="Volume Diário (Clique na barra para filtrar)"
    )
    
    # Esconde os rótulos dos zeros para não poluir o gráfico
    fig_bar.for_each_trace(lambda t: t.update(
        text=['' if v == 0 else str(int(v)) for v in t.y],
        texttemplate='%{text}',
        textposition='outside',
        textfont=dict(size=12, weight='bold'),
        cliponaxis=False
    ))
    
    fig_bar.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis_title=None,
        yaxis_title=None,
        showlegend=False,
        margin=dict(t=40, r=20, l=20, b=20),
        height=380
    )
    
    # Força um tick por dia
    fig_bar.update_xaxes(
        tickformat="%d/%m",
        dtick=86400000  # 1 dia em milissegundos
    )
    
    # EXIBIÇÃO COM SELEÇÃO (FEATURE NOVA DO STREAMLIT)
    evento_selecao = st.plotly_chart(fig_bar, use_container_width=True, on_select="rerun")

# --- LÓGICA DE FILTRO CRUZADO (CROSS-FILTERING) ---
# Se o usuário clicou numa barra, capturamos o Ponto
filtro_interativo_ativo = False
df_final_display = df_filtered.copy()

if evento_selecao and "selection" in evento_selecao:
    # Verifica se houve clique em algum ponto
    points = evento_selecao["selection"]["points"]
    if points:
        # Pega a data e o tipo clicados
        ponto_clicado = points[0]
        try:
            # Tenta pegar pelo label (x) ou customdata
            data_clicada = ponto_clicado.get("x")
            # Se for barra empilhada, o curve_number pode indicar o tipo, mas o jeito mais seguro
            # é filtrar apenas pela DATA clicada para ver o detalhe daquele dia
            if data_clicada:
                filtro_interativo_ativo = True
                # Filtra o DataFrame FINAL (Tabela e Rosca) para o dia clicado
                df_final_display = df_filtered[df_filtered['data'].astype(str).str.contains(data_clicada[:10])]
                st.toast(f"🔎 Filtrando detalhes para o dia: {data_clicada[:10]}")
        except:
            pass

# --- GRÁFICO DE ROSCA (REACTIVO AO CLIQUE DA BARRA) ---
with g2:
    titulo_rosca = "Distribuição (Dia Selecionado)" if filtro_interativo_ativo else "Distribuição Total (Período)"
    st.subheader(f"{titulo_rosca}")
    
    df_pie = df_final_display.groupby('Tipo')['Qtd'].sum().reset_index()
    total_pie = df_pie['Qtd'].sum()
    
    fig_pie = go.Figure(data=[go.Pie(
        labels=df_pie['Tipo'], 
        values=df_pie['Qtd'],
        hole=.6,
        textinfo='label+percent', # Mostra Nome + %
        marker=dict(colors=[
            '#0083b8' if t == 'BITRUCK' else "#8a3131"
            for t in df_pie['Tipo']
        ])
    )])
    
    fig_pie.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(orientation="h", y=-0.1),
        margin=dict(t=0, b=0, l=0, r=0),
        height=380,
        annotations=[dict(text=str(total_pie), x=0.5, y=0.5, font_size=40, showarrow=False, font_color="white", font_weight="bold")]
    )
    
    st.plotly_chart(fig_pie, use_container_width=True)

# --- 8. KPIS (MÉTRICAS) ---
# Calculados sobre o df_final_display (que reage ao clique)
k1, k2, k3 = st.columns(3)
total_disp = df_final_display['Qtd'].sum()
k1.metric("Veículos Parados", total_disp)

if not filtro_interativo_ativo:
    # Se não filtrou um dia específico, mostra média
    media = df_filtered.groupby('data')['Qtd'].sum().mean()
    k2.metric("Média Diária", f"{media:.1f}")
else:
    # Se filtrou um dia, mostra quantos % isso representa do total do período
    perc_do_total = (total_disp / df_filtered['Qtd'].sum()) * 100
    k2.metric("Impacto no Período", f"{perc_do_total:.1f}%")

top_tipo = df_final_display.groupby('Tipo')['Qtd'].sum().idxmax()
k3.metric("Maior Gargalo", top_tipo)

st.markdown("---")

# --- 9. TABELA DETALHADA (REATIVA) ---
titulo_tabela = "Detalhamento do Dia" if filtro_interativo_ativo else "Visão Geral (Heatmap)"
st.subheader(titulo_tabela)

if filtro_interativo_ativo:
    # Se filtrou um dia, mostra a lista crua daquele dia
    st.dataframe(
        df_final_display[['data', 'Tipo', 'Qtd', 'Porcentagem', 'Total_Dia']].style.format({
            'Porcentagem': '{:.1%}',
            'data': lambda x: x.strftime('%d/%m/%Y')
        }),
        use_container_width=True,
        hide_index=True
    )
    if st.button("🔄 Limpar Filtro de Clique"):
        st.rerun()
else:
    # Se é visão geral, mostra o Heatmap Pivotado
    df_show = df_filtered.copy()
    df_show['data_fmt'] = df_show['data'].dt.strftime('%d/%m/%Y')
    df_pivot = df_show.pivot_table(index='data_fmt', columns='Tipo', values='Qtd', aggfunc='sum', fill_value=0)
    df_pivot['TOTAL'] = df_pivot.sum(axis=1)
    # Ordenação por data
    df_pivot = df_pivot.sort_index(key=lambda x: pd.to_datetime(x, format='%d/%m/%Y'))

    st.dataframe(
        df_pivot.style.background_gradient(cmap="Reds", subset=['TOTAL']),
        use_container_width=True
    )