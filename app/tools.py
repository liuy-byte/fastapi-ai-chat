"""模型可以调用的工具。全部本地计算，不调外部接口，跑起来不依赖任何第三方服务。"""

import ast
import operator
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain.tools import tool


@tool
def current_time(timezone: str = "Asia/Shanghai") -> str:
    """查询某个时区的当前日期和时间。timezone 用 IANA 名称，例如 Asia/Shanghai、America/New_York。"""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        return f"不认识的时区：{timezone}"
    return now.strftime("%Y-%m-%d %H:%M:%S %A") + f"（{timezone}）"


@tool
def days_between(start: str, end: str) -> str:
    """计算两个日期相差多少天，日期格式 YYYY-MM-DD。"""
    try:
        d1, d2 = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return "日期格式不对，要 YYYY-MM-DD"
    return f"{start} 到 {end} 相差 {(d2 - d1).days} 天"


# 计算器只认这几种运算，其他语法一律拒绝，不用 eval
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("指数太大")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("只支持数字和 + - * / // % ** 运算")


@tool
def calculator(expression: str) -> str:
    """计算一个算术表达式，例如 (1200 * 0.85) / 3。只支持数字和 + - * / // % ** 括号。"""
    try:
        result = _eval(ast.parse(expression, mode="eval").body)
    except (SyntaxError, ValueError, ZeroDivisionError) as e:
        return f"算不了：{e}"
    return str(result)


# 工具注册表：对话里存的是名字，用的时候按名字取
TOOLS = {t.name: t for t in (current_time, days_between, calculator)}
