"""Rule layer.

Each rule lives in its own module and is a small class with class-level
metadata (``rule_id``, ``title``, ``knowledge_refs``) and an ``evaluate``
method that takes a :class:`RuleContext` and returns a list of
:class:`Finding` objects. Step 15 builds the registry and dispatcher;
this package exists in step 11 as a flat namespace of leaf rules.
"""

from spec_check.rules.ambiguous_criterion import AmbiguousCriterion
from spec_check.rules.base import Rule, RuleContext
from spec_check.rules.criterion_without_test import CriterionWithoutTest
from spec_check.rules.large_diff_without_spec import LargeDiffWithoutSpec
from spec_check.rules.missing_ac_section import MissingAcSection
from spec_check.rules.missing_acceptance_criteria import MissingAcceptanceCriteria
from spec_check.rules.multiple_specs_referenced import MultipleSpecsReferenced
from spec_check.rules.scope_creep import ScopeCreep
from spec_check.rules.spec_modified_after_branch import SpecModifiedAfterBranch
from spec_check.rules.untestable_criterion import UntestableCriterion

__all__ = [
    "AmbiguousCriterion",
    "CriterionWithoutTest",
    "LargeDiffWithoutSpec",
    "MissingAcSection",
    "MissingAcceptanceCriteria",
    "MultipleSpecsReferenced",
    "Rule",
    "RuleContext",
    "ScopeCreep",
    "SpecModifiedAfterBranch",
    "UntestableCriterion",
]
