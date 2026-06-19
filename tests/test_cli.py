# tests/test_cli.py
from pathlib import Path
import pytest
from portfolio.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "trade_republic_networth.txt"
CONFIG = """
base_currency: EUR
categories:
  gold: {target_weight: 0.20, isins: [IE00B4ND3602]}
  global-equity: {target_weight: 0.50, isins: [IE00B4L5Y983]}
  bonds: {target_weight: 0.10, isins: []}
  cash: {target_weight: 0.20, isins: []}
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CONFIG)
    acc = tmp_path / "accounts"
    lines = [ln for ln in FIXTURE.read_text().splitlines() if ln.strip()]
    from portfolio.sources import trade_republic
    monkeypatch.setattr(trade_republic, "extract_lines", lambda src: lines)
    return cfg, acc


def test_ingest_writes_snapshot(env, tmp_path, capsys):
    cfg, acc = env
    fake_pdf = tmp_path / "nw.pdf"
    fake_pdf.write_text("x")
    rc = main(["--config", str(cfg), "--accounts-dir", str(acc),
               "ingest", str(fake_pdf), "--yes"])
    assert rc == 0
    assert (acc / "trade_republic.json").exists()


def test_show_after_ingest(env, tmp_path, capsys):
    cfg, acc = env
    fake_pdf = tmp_path / "nw.pdf"
    fake_pdf.write_text("x")
    main(["--config", str(cfg), "--accounts-dir", str(acc), "ingest", str(fake_pdf), "--yes"])
    capsys.readouterr()
    rc = main(["--config", str(cfg), "--accounts-dir", str(acc), "show"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "5,000.00" in out or "5000.00" in out  # net worth total
    assert "IE00BK5BQT80" in out  # FTSE All-World is uncategorized → flagged


def test_check_flags_uncategorized(env, tmp_path, capsys):
    cfg, acc = env
    fake_pdf = tmp_path / "nw.pdf"
    fake_pdf.write_text("x")
    main(["--config", str(cfg), "--accounts-dir", str(acc), "ingest", str(fake_pdf), "--yes"])
    capsys.readouterr()
    rc = main(["--config", str(cfg), "--accounts-dir", str(acc), "check"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "IE00BK5BQT80" in out


def test_add_category(env, tmp_path):
    cfg, acc = env
    from portfolio.config import load_config
    rc = main(["--config", str(cfg), "--accounts-dir", str(acc), "add-category", "us-etf"])
    assert rc == 0
    assert load_config(cfg).categories["us-etf"].target_weight == 0.0


def test_move_isin_command(env, tmp_path):
    cfg, acc = env
    from portfolio.config import load_config
    rc = main(["--config", str(cfg), "--accounts-dir", str(acc),
               "move-isin", "IE00B4ND3602", "global-equity"])
    assert rc == 0
    c = load_config(cfg)
    assert "IE00B4ND3602" in c.categories["global-equity"].isins
    assert "IE00B4ND3602" not in c.categories["gold"].isins


def test_rename_category_command(env, tmp_path):
    cfg, acc = env
    from portfolio.config import load_config
    rc = main(["--config", str(cfg), "--accounts-dir", str(acc),
               "rename-category", "gold", "precious-metals"])
    assert rc == 0
    assert "precious-metals" in load_config(cfg).categories


def test_remove_category_command(env, tmp_path):
    cfg, acc = env
    from portfolio.config import load_config
    main(["--config", str(cfg), "--accounts-dir", str(acc), "add-category", "spare"])
    rc = main(["--config", str(cfg), "--accounts-dir", str(acc), "remove-category", "spare"])
    assert rc == 0
    assert "spare" not in load_config(cfg).categories


def test_remove_category_non_empty_fails(env, tmp_path, capsys):
    cfg, acc = env
    rc = main(["--config", str(cfg), "--accounts-dir", str(acc), "remove-category", "gold"])
    assert rc == 1
