"""阶段八 8.3 策略生成三级校验测试。"""

from app.agent.strategy_validator import validate_strategy

_GOOD_CODE = """def initialize(context):
    context.params["fast"] = 5

def on_bar(bar, context):
    if bar["close"] > context.params["fast"]:
        context.buy(100)
"""


def test_validate_good_code_passes():
    result = validate_strategy(_GOOD_CODE)
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_syntax_error():
    result = validate_strategy("def on_bar(bar, context):\n  x = ")
    assert result["valid"] is False
    assert result["errors"][0]["line"] is not None


def test_validate_missing_on_bar():
    result = validate_strategy("def initialize(context):\n    pass\n")
    assert result["valid"] is False
    assert any("on_bar" in e["message"] for e in result["errors"])


def test_validate_missing_initialize():
    result = validate_strategy("def on_bar(bar, context):\n    pass\n")
    assert result["valid"] is False
    assert any("initialize" in e["message"] for e in result["errors"])


def test_validate_wrong_signature():
    code = "def initialize(context):\n    pass\n\ndef on_bar(ctx, bar, extra):\n    pass\n"
    result = validate_strategy(code)
    assert result["valid"] is False
    assert any("on_bar 参数" in e["message"] for e in result["errors"])


def test_validate_import_rejected():
    code = "import os\n\ndef initialize(context):\n    pass\n\ndef on_bar(bar, context):\n    pass\n"
    result = validate_strategy(code)
    assert result["valid"] is False
    assert any("import" in e["message"] for e in result["errors"])


def test_validate_runtime_name_error_with_line():
    code = "def initialize(context):\n    pass\n\ndef on_bar(bar, context):\n    y = undefined_var\n    context.buy(100)\n"
    result = validate_strategy(code)
    assert result["valid"] is False
    err = result["errors"][0]
    assert err["line"] == 5
    assert "undefined_var" in err["message"]


def test_validate_runtime_zero_division():
    code = "def initialize(context):\n    pass\n\ndef on_bar(bar, context):\n    x = 1 / 0\n"
    result = validate_strategy(code)
    assert result["valid"] is False
    assert "ZeroDivisionError" in result["errors"][0]["message"]


def test_validate_runtime_index_error():
    code = "def initialize(context):\n    pass\n\ndef on_bar(bar, context):\n    x = context.closes[0]\n"
    result = validate_strategy(code)
    assert result["valid"] is False
    assert "IndexError" in result["errors"][0]["message"]
