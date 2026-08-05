"""Symbol parsing utilities.

Rules:
 - `sh6xxxxx` (or `sh900xxx`) → A_STOCK on Shanghai
 - `sh000xxx` / `sh999xxx` → INDEX on Shanghai
 - `sz00xxxx` / `sz30xxxx` / `sz20xxxx` → A_STOCK on Shenzhen
 - `sz39xxxx` → INDEX on Shenzhen
 - `sz15xxxx` / `sz16xxxx` / `sz18xxxx` → LOF_FUND on Shenzhen
 - `sh50xxxx` / `sh51xxxx` / `sh52xxxx` → LOF_FUND on Shanghai
 - `bj8xxxxx` / `bj4xxxxx` → A_STOCK on BeiJing exchange
"""

import re
from typing import Tuple

from src.common.models import SymbolType

_PATTERN = re.compile(r"^(sh|sz|bj)(\d{6})$")


def parse_symbol(symbol: str) -> Tuple[SymbolType, str, str]:
    """Return (symbol_type, market_prefix, pure_code).

    Raises ValueError when the symbol string is malformed.
    """
    if not symbol:
        raise ValueError("symbol must not be blank")

    m = _PATTERN.match(symbol.lower())
    if not m:
        raise ValueError(
            f"invalid symbol '{symbol}', expected sh|sz|bj + 6 digits"
        )

    prefix, code = m.group(1), m.group(2)

    if prefix == "sh":
        if code.startswith("000") or code.startswith("999"):
            return SymbolType.INDEX, prefix, code
        if code.startswith(("50", "51", "52")):
            return SymbolType.LOF_FUND, prefix, code
        return SymbolType.A_STOCK, prefix, code

    if prefix == "sz":
        if code.startswith("39"):
            return SymbolType.INDEX, prefix, code
        if code.startswith(("15", "16", "18")):
            return SymbolType.LOF_FUND, prefix, code
        return SymbolType.A_STOCK, prefix, code

    return SymbolType.A_STOCK, prefix, code
