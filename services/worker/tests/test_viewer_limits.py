"""The web viewer opens only what the worker could check, so their model limits must be equal.

The viewer's limits are TypeScript (`apps/web/src/constants/viewer.constant.ts`); this reads
their numeric expressions with a tiny evaluator (numbers, `*`, `+` and earlier constants only)
and compares them with the worker's (KILN-9 review).
"""

import ast
import operator
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from kiln_worker import constants

_WEB = Path(__file__).resolve().parents[3] / "apps/web/src/constants/viewer.constant.ts"
_DECLARATION = re.compile(r"^export const ([A-Z][A-Z0-9_]*)\s*=\s*([^;{]+);", re.MULTILINE)
_OPERATORS: dict[type[ast.operator], Callable[[int, int], int]] = {
    ast.Mult: operator.mul,
    ast.Add: operator.add,
}


def _web_constants() -> dict[str, int]:
    values: dict[str, int] = {}

    def evaluate(node: ast.expr) -> int:
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return node.value
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
        msg = f"not a plain number expression: {ast.dump(node)}"
        raise ValueError(msg)

    for name, expression in _DECLARATION.findall(_WEB.read_text()):
        if re.fullmatch(r"[\w\s*+()]+", expression):
            values[name] = evaluate(ast.parse(" ".join(expression.split()), mode="eval").body)
    return values


@pytest.mark.parametrize(
    ("web", "worker"),
    [
        ("MODEL_VIEWER_MAX_BYTES", "MODEL_MAX_BYTES"),
        ("GLB_MAX_JSON_BYTES", "MODEL_MAX_JSON_BYTES"),
        ("MODEL_MAX_OBJECTS", "MODEL_MAX_OBJECTS"),
        ("MODEL_MAX_TRIANGLES", "MODEL_MAX_TRIANGLES"),
        ("MODEL_MAX_VERTICES", "MODEL_MAX_VERTICES"),
        ("MODEL_MAX_ACCESSOR_ELEMENTS", "MODEL_MAX_ACCESSOR_ELEMENTS"),
    ],
)
def test_the_web_viewer_and_the_worker_have_the_same_model_limits(web: str, worker: str) -> None:
    assert _web_constants()[web] == getattr(constants, worker)
