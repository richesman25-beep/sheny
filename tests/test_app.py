from pathlib import Path
from types import SimpleNamespace
import streamlit as st
from streamlit.testing.v1 import AppTest
from trading_analysis_system import MarketDataSimulator


def test_demo_interface_and_parameters():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "📈 Atelier Trading"
    assert len(app.tabs) == 4
    assert any("fictifs" in w.value for w in app.warning)
    assert any(m.label == "Capital final simulé" for m in app.metric)
    capital = next(n for n in app.number_input if n.label.startswith("Capital"))
    capital.set_value(5000).run()
    assert not app.exception
    source = app.radio[0]
    source.set_value("Importer un CSV").run()
    assert not app.exception
    assert any("Importez votre CSV" in w.value for w in app.warning)


def test_csv_analysis_in_interface(monkeypatch):
    payload = MarketDataSimulator.generate_ohlcv(300).to_csv().encode()
    uploaded = SimpleNamespace(size=len(payload), getvalue=lambda: payload)
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    app.radio[0].set_value("Importer un CSV").run()
    assert not app.exception
    assert any("Données importées" in s.value for s in app.success)
    assert any(m.label == "Capital final simulé" for m in app.metric)


def test_csv_error_is_shown_without_crash(monkeypatch):
    payload = b"timestamp,open,high,low,close,volume\ninvalid,1,2,1,2,100\n"
    uploaded = SimpleNamespace(size=len(payload), getvalue=lambda: payload)
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: uploaded)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    app.radio[0].set_value("Importer un CSV").run()
    assert not app.exception
    assert len(app.error) == 1
