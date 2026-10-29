"""Interface locale : streamlit run app.py."""
from dataclasses import asdict
from io import BytesIO
import json

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from trading_analysis_system import (
    EducationalTradingEngine, MarketDataSimulator, Settings, backtest, load_csv,
)

st.set_page_config(page_title="Atelier Trading", page_icon="📈", layout="wide")
st.title("📈 Atelier Trading")
st.caption("Analyse technique · gestion du risque · simulation historique")
st.info("Outil pédagogique : aucun ordre réel n’est envoyé. Un signal ou un bon résultat passé ne garantit aucun gain.")

with st.sidebar:
    st.header("Vos données")
    source = st.radio("Source", ["Démonstration", "Importer un CSV"])
    symbol = st.text_input("Nom de l’actif", "DEMO")
    upload = None
    if source == "Importer un CSV":
        upload = st.file_uploader("Fichier OHLCV UTF-8", type=["csv"])
        st.caption("Bougies clôturées uniquement. Dates ISO 8601 ; open, high, low, close, volume. Prix et capital dans la même devise.")
    else:
        bars = st.slider("Nombre de bougies fictives", 250, 5000, 750, step=50)
        seed = st.number_input("Scénario de démonstration", 0, 10000, 42)
    st.header("Votre risque")
    capital = st.number_input("Capital (devise de cotation)", min_value=1.0, value=10000.0, step=100.0)
    risk = st.number_input("Risque maximal par position (%)", min_value=0.1, max_value=100.0, value=1.0, step=0.1)
    with st.expander("Paramètres de stratégie et coûts"):
        atr_multiple = st.number_input("Distance du stop × ATR", min_value=0.1, max_value=10.0, value=1.5, step=0.1)
        reward = st.number_input("Ratio gain/risque brut", min_value=2.0, max_value=10.0, value=2.0, step=0.5)
        proximity = st.number_input("Distance maximale à l’EMA 50 (%)", min_value=0.1, max_value=10.0, value=1.5, step=0.1)
        fee = st.number_input("Frais par transaction (%)", min_value=0.0, max_value=5.0, value=0.1, step=0.01)
        slip = st.number_input("Glissement par exécution (%)", min_value=0.0, max_value=5.0, value=0.05, step=0.01)
    allow_short = st.checkbox("Simuler aussi les ventes à découvert", value=False)
    st.caption("Simulation sans levier : exposition plafonnée au capital. La vente à découvert reste un modèle simplifié sans financement ni liquidation.")


@st.cache_data(show_spinner=False)
def demo_data(bars, seed):
    return MarketDataSimulator.generate_ohlcv(bars=bars, seed=seed)


@st.cache_data(show_spinner=False, max_entries=5)
def historical(data, settings, shorts):
    return backtest(data, settings, shorts)


try:
    settings = Settings(capital, risk, atr_multiple, reward, proximity, fee, slip)
    if source == "Importer un CSV":
        if upload is None:
            st.warning("Importez votre CSV pour analyser des prix réels, ou choisissez Démonstration.")
            st.code("timestamp,open,high,low,close,volume\n2026-01-01T00:00:00Z,100,102,99,101,1200")
            st.caption("Minimum : 200 lignes pour l’analyse, 202 pour la simulation. La ligne ci-dessus montre seulement le format.")
            st.stop()
        if upload.size > 20 * 1024 * 1024:
            raise ValueError("Le fichier dépasse 20 Mo. Réduisez la période exportée.")
        data = load_csv(BytesIO(upload.getvalue()))
        if len(data) > 50000:
            raise ValueError("Limite interactive : 50 000 bougies. Réduisez la période ou utilisez le moteur Python.")
        st.success("Données importées depuis votre CSV. Leur provenance et leur exactitude restent à vérifier.")
    else:
        data = demo_data(bars, int(seed))
        st.warning("DÉMONSTRATION — tous les prix affichés sont fictifs, même si vous changez le nom de l’actif.")
    analysis = EducationalTradingEngine(symbol=symbol, settings=settings).analyze(data)
except (ValueError, TypeError, OverflowError) as exc:
    st.error(str(exc))
    st.stop()

st.caption(f"{len(data):,} bougies · {data.index[0].isoformat()} → {data.index[-1].isoformat()} · horaires UTC")
cols = st.columns(4)
cols[0].metric("Dernier cours", f"{analysis['last_price']:,.4f}")
cols[1].metric("Tendance", analysis["trend_regime"])
cols[2].metric("RSI · 14", f"{analysis['indicators']['rsi']:.1f}")
cols[3].metric("ATR · 14", f"{analysis['indicators']['atr']:,.4f}")

chart_tab, signal_tab, history_tab, guide_tab = st.tabs(["Marché", "Scénario et risque", "Simulation historique", "Mode d’emploi"])

with chart_tab:
    frame = analysis["df_analyzed"].tail(1000)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.05)
    fig.add_trace(go.Candlestick(x=frame.index, open=frame.open, high=frame.high,
                                low=frame.low, close=frame.close, name="Prix"), row=1, col=1)
    for period, color in [(20, "#2dd4bf"), (50, "#fbbf24"), (200, "#a78bfa")]:
        fig.add_trace(go.Scatter(x=frame.index, y=frame[f"ema_{period}"],
                                name=f"EMA {period}", line=dict(color=color, width=1.5)), row=1, col=1)
    for key in ("support", "resistance"):
        fig.add_trace(go.Scatter(x=frame.index, y=frame[key], name=key,
                                line=dict(width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=frame.index, y=frame.rsi, name="RSI", line=dict(color="#60a5fa")), row=2, col=1)
    fig.add_hrect(y0=40, y1=60, fillcolor="#60a5fa", opacity=0.1, line_width=0, row=2, col=1)
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    fig.update_layout(height=650, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Le graphique affiche les 1 000 dernières bougies au maximum. Le calcul utilise toutes les données importées.")
    st.download_button("Télécharger les données / modèle CSV", data.to_csv().encode("utf-8"),
                       "donnees_ohlcv.csv", "text/csv")

with signal_tab:
    st.subheader("Conditions sur la dernière bougie clôturée")
    for label, passed in analysis["checklist"].items():
        st.write(("✅ " if passed else "⬜ ") + label)
    sig = analysis["signal"]
    if sig:
        st.success(f"Scénario détecté : {sig.direction}")
        st.caption("Niveaux indicatifs au dernier cours. Recalculer la taille si le prix d’exécution change.")
        c = st.columns(3)
        for col, label, value in zip(c, ["Entrée indicative", "Stop indicatif", "Objectif indicatif"],
                                      [sig.entry_price, sig.stop_loss, sig.take_profit]):
            col.metric(label, f"{value:,.6f}")
        p = sig.position_sizing
        st.write(f"Taille théorique : **{p['units']:,.6f} unités** · exposition : **{p['notional_value']:,.2f}**")
        st.write(f"Perte estimée au stop avec coûts : **{p['risk_amount_usd']:,.2f}** / budget : **{p['risk_budget']:,.2f}**")
        st.write(f"Ratio gain/risque brut : **{sig.risk_reward_ratio:.1f}**. Le ratio net diminue avec les coûts.")
    else:
        st.info("Aucun scénario conforme : les conditions ne sont pas toutes réunies, ou les niveaux calculés sont invalides.")
    st.warning("Un stop ne garantit pas la perte maximale : un gap ou une exécution défavorable peut dépasser le budget.")
    report = {k: v for k, v in analysis.items() if k != "df_analyzed"}
    report["signal"] = asdict(sig) if sig else None
    report["settings"] = asdict(settings)
    report["data_source"] = source
    st.download_button("Exporter le rapport JSON", json.dumps(report, ensure_ascii=False, indent=2),
                       "rapport_analyse.json", "application/json")

with history_tab:
    st.subheader("Tester les règles sur votre historique")
    st.caption("200 premières bougies réservées aux indicateurs. Une position à la fois ; achat uniquement par défaut.")
    if len(data) < 202:
        st.info("Ajoutez des données : au moins 202 bougies sont nécessaires.")
    elif st.checkbox("Calculer la simulation", value=True):
        with st.spinner("Simulation des entrées, sorties et coûts…"):
            result = historical(data, settings, allow_short)
        m = result["metrics"]
        c = st.columns(4)
        c[0].metric("Capital final simulé", f"{m['final_balance']:,.2f}")
        c[1].metric("Rendement net simulé", f"{m['return_pct']:.2f} %")
        c[2].metric("Baisse maximale", f"{m['max_drawdown_pct']:.2f} %")
        c[3].metric("Positions simulées", m["trades"])
        curve = go.Figure(go.Scatter(x=result["equity"].index, y=result["equity"], mode="lines", name="Capital"))
        curve.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="Devise de cotation")
        st.plotly_chart(curve, use_container_width=True)
        if m["trades"]:
            st.write(f"Positions gagnantes : {m['win_rate_pct']:.1f} % · frais cumulés : {m['fees']:.2f}")
            st.dataframe(result["trades"], hide_index=True, use_container_width=True)
            st.download_button("Télécharger le journal CSV", result["trades"].to_csv(index=False).encode("utf-8"),
                               "journal_simulation.csv", "text/csv")
        else:
            st.info("Aucune position dans cette période : aucun résultat de performance ne peut être déduit.")
    st.markdown("""**Hypothèses du modèle**

- Signal sur une bougie clôturée ; entrée à l’ouverture suivante, avec glissement adverse.
- Frais sur l’entrée et la sortie. Aucun levier ; le capital et la taille évoluent après chaque position.
- Si stop et objectif sont touchés sur la même bougie, le stop est retenu ; un gap au stop utilise le cours d’ouverture.
- Une position encore ouverte est liquidée au dernier cours de l’échantillon (`fin_echantillon`).
- Le ratio visé est brut. Spread, financement, liquidité, fiscalité et contraintes de lot ne sont pas modélisés.
- Résultats sur l’échantillon fourni uniquement : aucune validation hors échantillon ni preuve de rentabilité.
""")

with guide_tab:
    st.markdown("""### Démarrage en trois étapes

1. Explorez la **Démonstration** pour comprendre les graphiques et la checklist.
2. Exportez au moins **200 bougies clôturées** depuis votre fournisseur de marché et importez le CSV. Pour une simulation utile, préférez un historique nettement plus long.
3. Ajustez le capital, le risque et les coûts de votre marché, puis consultez le scénario et la simulation. Exportez vos résultats si nécessaire.

### Format des données

Colonnes : `timestamp,open,high,low,close,volume`. Dates ISO 8601 (exemple : `2026-01-01T00:00:00Z`). Les dates sans fuseau sont interprétées en UTC. Chaque date doit être unique. Les lignes sont triées automatiquement ; les bougies invalides sont refusées. Le fichier ne doit contenir aucune bougie encore en formation.

Les prix et le capital doivent être dans la même devise. Pour les produits dérivés, les lots Forex ou les contrats à multiplicateur, la taille en unités n’est pas directement une taille d’ordre.

### Comprendre la stratégie

Les EMA 20/50/200 doivent être alignées avec le prix ; le cours doit être proche de l’EMA 50 et le RSI compris entre 40 et 60. Le stop utilise l’ATR de Wilder. Les supports/résistances affichés sont simplement les extrêmes des 30 dernières bougies, pas des pivots confirmés.

### Ce que l’application ne fait pas

Pas de connexion à un courtier, pas de cours en direct, pas de sauvegarde automatique des imports ou journaux. Le nom de l’actif est une étiquette : il ne télécharge aucune donnée. Les exports doivent être conservés par vos soins. Utilisez d’abord un compte de démonstration chez votre fournisseur si vous souhaitez pratiquer.
""")
