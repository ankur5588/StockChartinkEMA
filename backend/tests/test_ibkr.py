"""Tests for IBKR client functions (S&P 500 classification, category pct)."""
import os
import tempfile
import pytest

from ibkr_client import is_snp500, get_category_pct, load_snp500

SNP500_CSV = """symbol,name,sector
AAPL,Apple Inc,Technology
MSFT,Microsoft Corp,Technology
GOOGL,Alphabet Inc,Communication
AMZN,Amazon.com Inc,Consumer
NVDA,NVIDIA Corp,Technology
META,Meta Platforms Inc,Communication
BRK.B,Berkshire Hathaway,Financial
TSLA,Tesla Inc,Consumer
UNH,UnitedHealth Group,Health
JPM,JPMorgan Chase,Financial
"""


def _load_csv(content):
    """Helper: write content to tempfile, load it, return path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    f.write(content)
    f.close()
    load_snp500(f.name)
    return f.name


class TestSnp500Classification:
    def test_load_and_identify_sp500(self):
        path = _load_csv(SNP500_CSV)
        try:
            assert is_snp500("AAPL") is True
            assert is_snp500("MSFT") is True
            assert is_snp500("GOOGL") is True
            assert is_snp500("AAPL ") is True
            assert is_snp500("aapl") is True
        finally:
            os.unlink(path)

    def test_non_sp500_symbol(self):
        path = _load_csv(SNP500_CSV)
        try:
            assert is_snp500("RANDOMCO") is False
            assert is_snp500("") is False
            assert is_snp500("AAPL2") is False
        finally:
            os.unlink(path)

    def test_empty_csv(self):
        path = _load_csv("symbol,name,sector\n")
        try:
            assert is_snp500("AAPL") is False
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        result = load_snp500("/nonexistent/path.csv")
        assert result == set()
        assert is_snp500("AAPL") is False


class TestGetCategoryPct:
    def test_sp500_returns_10pct(self):
        path = _load_csv(SNP500_CSV)
        try:
            assert get_category_pct("AAPL") == 0.10
            assert get_category_pct("NVDA") == 0.10
            assert get_category_pct("BRK.B") == 0.10
        finally:
            os.unlink(path)

    def test_non_sp500_returns_5pct(self):
        path = _load_csv(SNP500_CSV)
        try:
            assert get_category_pct("RANDOMCO") == 0.05
            assert get_category_pct("") == 0.05
        finally:
            os.unlink(path)

    def test_symbol_case_insensitive(self):
        path = _load_csv("symbol,name,sector\nAAPL,Apple,Technology\n")
        try:
            assert get_category_pct("aapl") == 0.10
            assert get_category_pct("Aapl") == 0.10
        finally:
            os.unlink(path)
