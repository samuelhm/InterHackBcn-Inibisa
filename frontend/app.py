import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
from datetime import date, timedelta
from sqlalchemy import create_engine, text

PAGE_SIZE = 30

st.set_page_config(
    page_title="Smart Demand Signals — Inibsa",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #0a1628 0%, #0d1f3c 100%);
    }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1a30 0%, #0e1e38 100%);
        border-right: 1px solid #1e3a5f;
    }
    [data-testid="stSidebar"] * { color: #e0e6ed !important; }
    section[data-testid="stSidebar"] label { color: #e0e6ed !important; }

    div[data-testid="stMetric"] {
        background: #152238;
        border: 1px solid #1e3a5f;
        border-radius: 8px;
        padding: 8px 12px !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    div[data-testid="stMetric"] label {
        color: #8fa3b8 !important;
        font-size: 0.68rem !important;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #e0e6ed !important;
        font-size: 1.2rem !important;
        font-weight: 700 !important;
    }

    [data-testid="stExpander"] {
        background: #152238 !important;
        border: 1px solid #1e3a5f !important;
        border-radius: 6px !important;
        margin-bottom: 2px !important;
    }
    [data-testid="stExpander"] summary {
        color: #e0e6ed !important;
        font-size: 0.82rem !important;
        padding: 4px 10px !important;
    }
    [data-testid="stExpander"]:hover { border-color: #2196F3 !important; }

    .stButton > button {
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 0.78rem !important;
        padding: 4px 12px !important;
        min-height: 0 !important;
        line-height: 1.3 !important;
        transition: all 0.15s !important;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-track { background: #0a1628; }
    ::-webkit-scrollbar-thumb { background: #1e3a5f; border-radius: 3px; }
    hr { border-color: #1e3a5f !important; margin: 4px 0 !important; }

    .stTabs [data-baseweb="tab-list"] { gap: 6px; background: transparent; }
    .stTabs [data-baseweb="tab"] {
        background: #152238;
        border: 1px solid #1e3a5f;
        border-radius: 6px 6px 0 0;
        color: #8fa3b8;
        padding: 6px 16px;
    }
    .stTabs [aria-selected="true"] {
        background: #1a3050 !important;
        color: #2196F3 !important;
        border-bottom: 2px solid #2196F3 !important;
    }

    div.row-widget.stButton { display: inline-block; }
</style>
""", unsafe_allow_html=True)

ALERT_COLORS = {
    "ventana_captura": "#4caf50",
    "reposicion": "#2196F3",
    "riesgo_fuga": "#ff9800",
    "cliente_perdido": "#ef5350",
}

ALERT_ICONS = {
    "ventana_captura": "\U0001F3AF",
    "reposicion": "\U0001F504",
    "riesgo_fuga": "\u26A0\uFE0F",
    "cliente_perdido": "\U0001F6AB",
}

PROFILE_COLORS = {
    "leal": "#4caf50",
    "promiscuo": "#ff9800",
    "marginal": "#ef5350",
}


def _hex_to_rgba(hex_color, alpha=0.12):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


@st.cache_resource
def get_engine():
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://admin_inibsa:inibsa_secret_2024@localhost:5432/inibsa_smart_signals",
    )
    return create_engine(db_url, pool_size=5, max_overflow=5, pool_pre_ping=True)


def _fmt(val, decimals=0):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if decimals == 0:
        return int(val)
    return round(float(val), decimals)


def _fmt_euro(val):
    v = _fmt(val)
    return f"\u20AC{v:,}" if v is not None else "—"


def _fmt_pct(val, decimals=0):
    v = _fmt(val, 2)
    return f"{v * 100:.{decimals}f}%" if v is not None else "—"


# ─── CACHED DATA LOADERS ────────────────────────────────────


@st.cache_data(ttl=300)
def load_filter_options():
    engine = get_engine()
    with engine.connect() as conn:
        provincias = pd.read_sql(
            text("SELECT DISTINCT provincia FROM alertas "
                 "WHERE prioridad > 100 AND feedback IS NULL ORDER BY provincia"),
            conn,
        )["provincia"].tolist()
        bloques = pd.read_sql(
            text("SELECT DISTINCT bloque::TEXT FROM alertas "
                 "WHERE prioridad > 100 AND feedback IS NULL ORDER BY bloque::TEXT"),
            conn,
        )["bloque"].tolist()
        familias_df = pd.read_sql(
            text("SELECT DISTINCT bloque::TEXT AS bloque, familia FROM alertas "
                 "WHERE prioridad > 100 AND feedback IS NULL ORDER BY bloque, familia"),
            conn,
        )
    return provincias, bloques, familias_df


@st.cache_data(ttl=120)
def load_dashboard_metrics():
    engine = get_engine()
    m = {}
    with engine.connect() as conn:
        m["pending"] = conn.execute(
            text("SELECT COUNT(*) FROM alertas WHERE prioridad > 100 AND feedback IS NULL")
        ).scalar() or 0
        m["solved_today"] = conn.execute(
            text("SELECT COUNT(*) FROM alertas "
                 "WHERE feedback IS NOT NULL AND fecha_feedback = CURRENT_DATE")
        ).scalar() or 0
        rate = conn.execute(text(
            "SELECT COALESCE(COUNT(*) FILTER (WHERE feedback = 1)::FLOAT "
            "/ NULLIF(COUNT(*), 0), 0) FROM alertas "
            "WHERE feedback IS NOT NULL AND fecha_feedback >= CURRENT_DATE - INTERVAL '30 days'"
        )).scalar()
        m["conversion_rate"] = round((rate or 0) * 100, 1)
        m["generated_today"] = conn.execute(
            text("SELECT COUNT(*) FROM alertas WHERE fecha = CURRENT_DATE AND prioridad > 100")
        ).scalar() or 0
        m["generated_yesterday"] = conn.execute(
            text("SELECT COUNT(*) FROM alertas "
                 "WHERE fecha = CURRENT_DATE - INTERVAL '1 day' AND prioridad > 100")
        ).scalar() or 0
        m["distribution"] = pd.read_sql(text(
            "SELECT tipo_alerta, COUNT(*) AS n FROM alertas "
            "WHERE prioridad > 100 AND feedback IS NULL GROUP BY tipo_alerta ORDER BY n DESC"
        ), conn)
        m["history"] = pd.read_sql(text(
            "SELECT fecha::DATE, COUNT(*) AS n FROM alertas "
            "WHERE prioridad > 100 AND fecha >= CURRENT_DATE - INTERVAL '14 days' "
            "GROUP BY fecha::DATE ORDER BY fecha"
        ), conn)
        m["feedback_breakdown"] = pd.read_sql(text(
            "SELECT feedback, COUNT(*) AS n FROM alertas "
            "WHERE feedback IS NOT NULL AND fecha_feedback >= CURRENT_DATE - INTERVAL '30 days' "
            "GROUP BY feedback"
        ), conn)
        m["by_province"] = pd.read_sql(text(
            "SELECT provincia, COUNT(*) AS n FROM alertas "
            "WHERE prioridad > 100 AND feedback IS NULL GROUP BY provincia ORDER BY n DESC LIMIT 10"
        ), conn)
        m["total_feedback"] = conn.execute(
            text("SELECT COUNT(*) FROM alertas WHERE feedback IS NOT NULL")
        ).scalar() or 0
    return m


@st.cache_data(ttl=30)
def load_alerts(_provincia, _tipo_tuple, _bloque, _familia, _min_pri, _max_pri, _search_text):
    engine = get_engine()
    conditions = ["prioridad > 100", "feedback IS NULL"]
    params = {}

    if _provincia:
        conditions.append("provincia = :prov")
        params["prov"] = _provincia
    if _tipo_tuple:
        parts = []
        for i, t in enumerate(_tipo_tuple):
            k = f"t{i}"
            parts.append(f":{k}")
            params[k] = t
        conditions.append(f"tipo_alerta IN ({','.join(parts)})")
    if _bloque:
        conditions.append("bloque::TEXT = :bloq")
        params["bloq"] = _bloque
    if _familia:
        conditions.append("familia = :fam")
        params["fam"] = _familia
    conditions.append("prioridad BETWEEN :min_p AND :max_p")
    params["min_p"] = _min_pri + 100
    params["max_p"] = _max_pri + 100
    if _search_text:
        conditions.append("LOWER(id_cliente) LIKE :srch")
        params["srch"] = f"%{_search_text.lower()}%"

    where = " AND ".join(conditions)
    query = text(f"""
        SELECT id_alerta, fecha::DATE AS fecha, id_cliente, familia,
               bloque::TEXT AS bloque, tipo_alerta, motivo, provincia,
               potencial_h, dias_desde_ultima_compra, impacto_estimado,
               urgencia_dias, ratio_promiscuidad, perfil_cliente,
               freq_media_dias, n_compras_hist, prioridad, score_conversion,
               alerta_frecuencia, alerta_volumen, alerta_ausencia, alerta_anomalia,
               (prioridad - 100) AS prioridad_ui
        FROM alertas WHERE {where} ORDER BY prioridad DESC
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params=params)


@st.cache_data(ttl=600)
def load_purchase_history(client_id, familia):
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(
            "SELECT v.fecha, SUM(v.valores_h) AS importe "
            "FROM ventas v JOIN producto p ON v.id_producto = p.id "
            "WHERE CAST(v.id_cliente AS TEXT) = :cid AND p.familia = :fam "
            "AND v.fecha >= CURRENT_DATE - INTERVAL '24 months' "
            "GROUP BY v.fecha ORDER BY v.fecha"
        ), conn, params={"cid": str(client_id), "fam": familia})


def submit_feedback(alert_id, value):
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text("UPDATE alertas SET feedback = :val, fecha_feedback = CURRENT_DATE "
                     "WHERE id_alerta = :aid"),
                {"val": value, "aid": alert_id},
            )


# ─── BADGE HELPERS ───────────────────────────────────────────


def alert_badge_html(tipo):
    c = ALERT_COLORS.get(tipo, "#666")
    icon = ALERT_ICONS.get(tipo, "")
    label = tipo.replace("_", " ").title()
    return (f'<span style="background:{c}20;color:{c};padding:1px 7px;'
            f'border-radius:14px;font-size:0.7rem;font-weight:600;'
            f'border:1px solid {c}40;white-space:nowrap">{icon} {label}</span>')


def profile_badge_html(perfil):
    c = PROFILE_COLORS.get(perfil, "#666")
    return (f'<span style="background:{c}20;color:{c};padding:1px 6px;'
            f'border-radius:10px;font-size:0.68rem">{perfil.title()}</span>')


def flag_dot(active, label):
    c = "#4caf50" if active else "#444"
    return f'<span style="color:{c};white-space:nowrap;font-size:0.72rem">{chr(9679) if active else chr(9675)} {label}</span>'


# ─── DASHBOARD TAB ───────────────────────────────────────────


def render_dashboard():
    st.markdown("## Panel de Control")
    st.markdown("---")

    m = load_dashboard_metrics()

    c1, c2, c3, c4 = st.columns(4)
    delta_today = m["generated_today"] - m["generated_yesterday"]
    c1.metric("Alertas Pendientes", m["pending"], delta_color="inverse")
    c2.metric("Resueltas Hoy", m["solved_today"])
    c3.metric("Tasa Conversión (30d)", f"{m['conversion_rate']}%")
    c4.metric("Nuevas Hoy", m["generated_today"],
              f"{delta_today:+d} vs ayer" if delta_today else None)

    st.markdown("---")

    col_a, col_b = st.columns(2)

    with col_a:
        dist = m["distribution"]
        if not dist.empty:
            fig = go.Figure(data=[go.Pie(
                labels=dist["tipo_alerta"].str.replace("_", " ").str.title(),
                values=dist["n"], hole=0.45,
                marker=dict(colors=[ALERT_COLORS.get(t, "#666") for t in dist["tipo_alerta"]],
                            line=dict(color="rgba(0,0,0,0.4)", width=1)),
                textinfo="label+percent", textfont=dict(color="#e0e6ed", size=11),
            )])
            fig.update_layout(
                title=dict(text="Distribución por Tipo de Alerta", font=dict(color="#e0e6ed", size=14)),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                height=360, showlegend=False, margin=dict(t=45, b=5, l=5, r=5),
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        prov = m["by_province"]
        if not prov.empty:
            fig2 = go.Figure(data=[go.Bar(
                y=prov["provincia"], x=prov["n"], orientation="h",
                marker=dict(color=prov["n"], colorscale="Blues",
                            line=dict(color="rgba(0,0,0,0.3)", width=1)),
                text=prov["n"], textposition="outside", textfont=dict(color="#e0e6ed"),
            )])
            fig2.update_layout(
                title=dict(text="Top 10 Provincias", font=dict(color="#e0e6ed", size=14)),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                height=360, yaxis=dict(autorange="reversed", color="#8fa3b8"),
                xaxis=dict(color="#8fa3b8", gridcolor="#1e3a5f"),
                margin=dict(t=45, b=5, l=5, r=25),
            )
            st.plotly_chart(fig2, use_container_width=True)

    history = m["history"]
    if not history.empty:
        all_dates = pd.date_range(start=date.today() - timedelta(days=13),
                                  end=date.today(), freq="D")
        hist_df = history.set_index("fecha").reindex(all_dates, fill_value=0).reset_index()
        hist_df.columns = ["fecha", "n"]
        fig3 = go.Figure(data=[go.Scatter(
            x=hist_df["fecha"], y=hist_df["n"], mode="lines+markers",
            line=dict(color="#2196F3", width=2.5),
            marker=dict(size=6, color="#2196F3"),
            fill="tozeroy", fillcolor="rgba(33,150,243,0.1)",
        )])
        fig3.update_layout(
            title=dict(text="Alertas Generadas (14 días)", font=dict(color="#e0e6ed", size=14)),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=280,
            xaxis=dict(color="#8fa3b8", gridcolor="#1e3a5f"),
            yaxis=dict(color="#8fa3b8", gridcolor="#1e3a5f"),
            margin=dict(t=45, b=5, l=5, r=5),
        )
        st.plotly_chart(fig3, use_container_width=True)

    col_c, col_d = st.columns(2)
    fb_data = m["feedback_breakdown"]
    pos = int(fb_data[fb_data["feedback"] == 1]["n"].sum()) if 1 in fb_data["feedback"].values else 0
    neg = int(fb_data[fb_data["feedback"] == 0]["n"].sum()) if 0 in fb_data["feedback"].values else 0
    col_c.metric("\u2705 Feedback Positivo (30d)", pos)
    col_d.metric("\u274C Feedback Negativo (30d)", neg)
    st.caption(f"Total feedback acumulado en BD: {m['total_feedback']} registros")


# ─── ALERTS TAB ──────────────────────────────────────────────


def render_alerts():
    st.markdown("## Alertas Comerciales")

    provincias, bloques, familias_df = load_filter_options()

    with st.sidebar:
        st.markdown("### \U0001F50D Filtros")
        st.markdown("---")
        provincia_filter = st.selectbox("Provincia", options=["Todas"] + provincias, key="filtro_prov")
        tipo_filter = st.multiselect(
            "Tipo de Alerta",
            options=["ventana_captura", "reposicion", "riesgo_fuga", "cliente_perdido"],
            default=[], format_func=lambda x: x.replace("_", " ").title(), key="filtro_tipo")
        bloque_filter = st.selectbox("Bloque", options=["Todos"] + bloques, key="filtro_bloque")
        fam_options = ["Todas"]
        if bloque_filter != "Todos":
            fam_options += familias_df[familias_df["bloque"] == bloque_filter]["familia"].tolist()
        else:
            fam_options += familias_df["familia"].tolist()
        familia_filter = st.selectbox("Familia", options=fam_options, key="filtro_fam")
        st.markdown("---")
        min_pri, max_pri = st.slider("Rango de Prioridad (UI 0\u2013100)", 0, 100, (0, 100), 5, key="filtro_pri")
        st.markdown("---")
        search_filter = st.text_input("\U0001F50E Buscar Cliente", placeholder="ID de cl\u00ednica...", key="filtro_search")
        st.markdown("---")
        st.markdown("### \U0001F4E5 Exportar")
        st.caption("Descarga las alertas visibles en CSV")

    prov = None if provincia_filter == "Todas" else provincia_filter
    bloq = None if bloque_filter == "Todos" else bloque_filter
    fam = None if familia_filter == "Todas" else familia_filter
    tipo_tuple = tuple(tipo_filter) if tipo_filter else None

    with st.spinner("Cargando alertas..."):
        df = load_alerts(prov, tipo_tuple, bloq, fam, min_pri, max_pri, search_filter)

    if df.empty:
        st.info("No se encontraron alertas con los filtros seleccionados.")
        return

    csv_data = df.to_csv(index=False).encode("utf-8")
    with st.sidebar:
        st.download_button(
            label="\U0001F4C4 Descargar CSV", data=csv_data,
            file_name=f"alertas_inibsa_{date.today().isoformat()}.csv", mime="text/csv")

    grouped = df.groupby("id_cliente")
    client_order = grouped["prioridad"].max().sort_values(ascending=False).index.tolist()
    total_clients = len(client_order)

    # ── Pagination ──
    if ("alert_page" not in st.session_state
            or st.session_state.get("alert_page_key") != _page_key(prov, tipo_tuple, bloq, fam, min_pri, max_pri, search_filter)):
        st.session_state.alert_page = 0
        st.session_state.alert_page_key = _page_key(prov, tipo_tuple, bloq, fam, min_pri, max_pri, search_filter)

    total_pages = max(1, (total_clients + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(st.session_state.alert_page, total_pages - 1)
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_clients)

    # ── Page controls (top) ──
    _render_pagination(page, total_pages, total_clients, total_clients, "top")

    st.markdown(f"Mostrando {start_idx + 1}\u2013{end_idx} de {total_clients} cl\u00ednicas")
    st.markdown("---")

    if "fb_done" not in st.session_state:
        st.session_state.fb_done = set()

    page_clients = client_order[start_idx:end_idx]

    for client_id in page_clients:
        client_alerts = df[df["id_cliente"] == client_id].sort_values("prioridad", ascending=False)
        top = client_alerts.iloc[0]
        children = client_alerts.iloc[1:] if len(client_alerts) > 1 else None

        if top["id_alerta"] in st.session_state.fb_done:
            continue

        top_icon = ALERT_ICONS.get(top["tipo_alerta"], "")
        top_tipo_label = top["tipo_alerta"].replace("_", " ").title()
        n_child = len(children) if children is not None else 0
        child_str = f"  +{n_child}" if n_child else ""

        expander_label = (
            f"{top_icon} {client_id}  "
            f"P:{int(top['prioridad_ui'])}  "
            f"{top['familia']}  "
            f"{top_tipo_label}  "
            f"{top['provincia']}"
            f"{child_str}"
        )

        with st.expander(expander_label):
            _render_alert_card(top)
            st.markdown("---")
            _render_feedback_buttons(top["id_alerta"])

            if children is not None and len(children) > 0:
                st.markdown("---")
                st.markdown(f"#### \U0001F53D {len(children)} alertas m\u00e1s del mismo cliente")
                for _, child in children.iterrows():
                    if child["id_alerta"] in st.session_state.fb_done:
                        continue
                    child_icon = ALERT_ICONS.get(child["tipo_alerta"], "")
                    child_label = child["tipo_alerta"].replace("_", " ").title()
                    child_exp = (
                        f"{child_icon} {child_label}  P:{int(child['prioridad_ui'])}  "
                        f"{child['familia']}  |  {str(child['motivo'])[:110]}..."
                    )
                    with st.expander(child_exp):
                        _render_alert_card(child)
                        st.markdown("---")
                        _render_feedback_buttons(child["id_alerta"], prefix="c")

    st.markdown("---")
    _render_pagination(page, total_pages, total_clients, total_clients, "bottom")


def _page_key(prov, tipo_tuple, bloq, fam, min_pri, max_pri, search):
    return hash((prov, tipo_tuple or (), bloq, fam, min_pri, max_pri, search or ""))


def _render_pagination(page, total_pages, total_items, total_alerts, position):
    c1, c2, c3, c4, c5 = st.columns([1, 1.5, 2, 1.5, 1])
    with c1:
        if st.button("\u25C0\u25C0", key=f"first_{position}", disabled=page == 0, use_container_width=True):
            st.session_state.alert_page = 0
            st.rerun()
    with c2:
        if st.button("\u25C0 Anterior", key=f"prev_{position}", disabled=page == 0, use_container_width=True):
            st.session_state.alert_page = page - 1
            st.rerun()
    with c3:
        st.markdown(f"<div style='text-align:center;color:#8fa3b8;font-size:0.82rem;padding-top:6px'>"
                    f"P\u00e1g {page + 1} / {total_pages}</div>", unsafe_allow_html=True)
    with c4:
        if st.button("Siguiente \u25B6", key=f"next_{position}", disabled=page >= total_pages - 1, use_container_width=True):
            st.session_state.alert_page = page + 1
            st.rerun()
    with c5:
        if st.button("\u25B6\u25B6", key=f"last_{position}", disabled=page >= total_pages - 1, use_container_width=True):
            st.session_state.alert_page = total_pages - 1
            st.rerun()


def _render_alert_card(alert):
    tipo = alert["tipo_alerta"]
    color = ALERT_COLORS.get(tipo, "#666")
    icon = ALERT_ICONS.get(tipo, "")
    tipo_label = tipo.replace("_", " ").title()

    # Compact motive box
    st.markdown(
        f"""<div style="background:{color}15;border-left:3px solid {color};
        padding:4px 10px;border-radius:4px;margin-bottom:4px">
        <strong style="color:{color};font-size:0.82rem">{icon} {tipo_label}</strong>
        <span style="color:#b0b8c4;font-size:0.78rem;margin-left:8px">{alert['motivo'][:200]}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    # Flags inline
    flag_html = " &nbsp;|&nbsp; ".join([
        flag_dot(alert.get("alerta_frecuencia", False), "Frec"),
        flag_dot(alert.get("alerta_volumen", False), "Vol"),
        flag_dot(alert.get("alerta_ausencia", False), "Aus"),
        flag_dot(alert.get("alerta_anomalia", False), "Anom"),
    ])
    st.markdown(f'<div style="font-size:0.72rem;margin-bottom:4px">{flag_html}</div>', unsafe_allow_html=True)

    # Compact metrics — single row using columns
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Prioridad", f"{_fmt(alert['prioridad_ui'])}/100")
    m2.metric("Score", f"{_fmt_pct(alert.get('score_conversion'))}")
    m3.metric("Impacto", _fmt_euro(alert.get("impacto_estimado")))
    m4.metric("Días sin compra", _fmt(alert.get("dias_desde_ultima_compra")))
    m5.metric("Urgencia", _fmt(alert.get("urgencia_dias")))
    m6.metric("Promisc.", f"{_fmt_pct(alert.get('ratio_promiscuidad'))}")

    # Profile + extra info
    perfil = alert.get("perfil_cliente", "")
    st.markdown(
        f"Perfil: {profile_badge_html(perfil)} &nbsp;|&nbsp; "
        f"Potencial: {_fmt_euro(alert.get('potencial_h'))} &nbsp;|&nbsp; "
        f"Compras hist: {_fmt(alert.get('n_compras_hist'))} &nbsp;|&nbsp; "
        f"Freq media: {_fmt(alert.get('freq_media_dias'), 1)}d",
        unsafe_allow_html=True,
    )

    # Purchase history chart
    purchase_df = load_purchase_history(alert["id_cliente"], alert["familia"])
    if not purchase_df.empty:
        fig = go.Figure(data=[go.Scatter(
            x=purchase_df["fecha"], y=purchase_df["importe"],
            mode="lines+markers", line=dict(color=color, width=1.5),
            marker=dict(size=3, color=color),
            fill="tozeroy", fillcolor=_hex_to_rgba(color, 0.12),
        )])
        fig.update_layout(
            title=dict(text=f"Historial: {alert['familia']}", font=dict(size=11, color="#8fa3b8")),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=180, xaxis=dict(color="#8fa3b8", gridcolor="#1e3a5f"),
            yaxis=dict(color="#8fa3b8", gridcolor="#1e3a5f", title="\u20AC"),
            margin=dict(t=30, b=5, l=45, r=5),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Sin historial de compras.")


def _render_feedback_buttons(alert_id, prefix=""):
    fb1, fb2, fb3 = st.columns([1, 1, 3])
    with fb1:
        if st.button("\u2705 Venta", key=f"{prefix}pos_{alert_id}", help="Registrar venta conseguida"):
            submit_feedback(alert_id, 1)
            st.session_state.fb_done.add(alert_id)
            st.cache_data.clear()
            st.success("Feedback registrado.")
            st.rerun()
    with fb2:
        if st.button("\u274C No inter\u00e9s", key=f"{prefix}neg_{alert_id}", help="Registrar sin inter\u00e9s"):
            submit_feedback(alert_id, 0)
            st.session_state.fb_done.add(alert_id)
            st.cache_data.clear()
            st.info("Feedback registrado.")
            st.rerun()


# ─── MAIN ────────────────────────────────────────────────────


def main():
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
        <h1 style="color:#2196F3;margin:0;font-size:1.5rem">🦷 Smart Demand Signals</h1>
    </div>
    <p style="color:#8fa3b8;font-size:0.9rem;margin-bottom:12px">
        Inibsa — Sistema inteligente de alertas comerciales para cl\u00ednicas dentales
    </p>
    """, unsafe_allow_html=True)

    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        st.error(f"Error de conexi\u00f3n a la base de datos: {e}")
        st.info("Aseg\u00farate de que la base de datos est\u00e9 corriendo (docker compose up db)")
        return

    tab1, tab2 = st.tabs(["\U0001F4CA Dashboard", "\U0001F514 Alertas"])
    with tab1:
        render_dashboard()
    with tab2:
        render_alerts()


if __name__ == "__main__":
    main()
