"""Hand-built fixtures for rule tests.

Two builders, designed so a rule test can compose precisely the inputs it
needs without touching git or Notion:

* :mod:`tests.fixtures.synthetic_spec` — small :class:`ParsedSpec` factory.
* :mod:`tests.fixtures.synthetic_diff` — small :class:`ParsedDiff` factory.
* :mod:`tests.fixtures.synthetic_manifest` — :class:`CheckManifest` shell.
* :func:`make_context` — wires the three above into a :class:`RuleContext`.
"""

from tests.fixtures.synthetic_diff import make_diff
from tests.fixtures.synthetic_manifest import make_manifest
from tests.fixtures.synthetic_rule_context import make_context
from tests.fixtures.synthetic_spec import make_criterion, make_spec

__all__ = [
    "make_context",
    "make_criterion",
    "make_diff",
    "make_manifest",
    "make_spec",
]
