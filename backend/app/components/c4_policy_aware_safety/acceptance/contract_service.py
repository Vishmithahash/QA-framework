"""Policy contract acceptance and lifecycle service."""

from datetime import datetime, timezone
from typing import Any
from app.components.c4_policy_aware_safety.contracts.policy import (
    ContractLifecycleStatus,
    PolicyContract,
    RuleLifecycleStatus,
)


class ContractAcceptanceService:
    """Manages the explicit acceptance workflow and version immutability."""

    @staticmethod
    def accept_contract(
        contract: PolicyContract,
        accepted_by: str,
        justification: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> PolicyContract:
        """
        Explicitly transition a validated contract to ACCEPTED.
        Fails if contract is not in VALIDATED status or has unresolved blocking issues.
        """
        if contract.lifecycle_status != ContractLifecycleStatus.VALIDATED:
            blocking = [i.message for i in contract.validation_issues if i.blocking]
            reasons = (
                "; ".join(blocking)
                if blocking
                else f"Current status is {contract.lifecycle_status}"
            )
            raise ValueError(
                f"Cannot accept contract '{contract.contract_id}' (v{contract.version}): "
                f"contract must be VALIDATED with zero blocking issues. Details: {reasons}"
            )

        now = datetime.now(timezone.utc)
        acceptance_meta = {
            "accepted_by": accepted_by,
            "justification": justification,
            "accepted_at": now.isoformat(),
            **(extra_metadata or {}),
        }

        # Accept all constituent rules
        for rule in contract.rules:
            rule.status = RuleLifecycleStatus.ACCEPTED
            rule.acceptance_metadata = acceptance_meta

        contract.lifecycle_status = ContractLifecycleStatus.ACCEPTED
        contract.acceptance_metadata = acceptance_meta
        contract.updated_at = now
        contract.content_hash = contract.compute_content_hash()
        return contract

    @staticmethod
    def create_new_version(
        existing_contract: PolicyContract,
    ) -> PolicyContract:
        """
        Create a new mutable DRAFT version when an accepted contract requires modification.
        Preserves original contract immutability.
        """
        if existing_contract.lifecycle_status != ContractLifecycleStatus.ACCEPTED:
            raise ValueError(
                "Only an accepted contract version can be forked to a new version."
            )

        now = datetime.now(timezone.utc)
        new_version_int = existing_contract.version + 1

        # Deep copy rules with bumped candidate statuses
        new_rules = [rule.model_copy(deep=True) for rule in existing_contract.rules]
        for rule in new_rules:
            rule.status = RuleLifecycleStatus.CANDIDATE
            rule.rule_version = new_version_int
            rule.acceptance_metadata = None

        new_contract = PolicyContract(
            contract_id=existing_contract.contract_id,
            project_id=existing_contract.project_id,
            version=new_version_int,
            lifecycle_status=ContractLifecycleStatus.DRAFT,
            rules=new_rules,
            referenced_artifact_versions=dict(
                existing_contract.referenced_artifact_versions
            ),
            content_hash="",
            validation_issues=[],
            acceptance_metadata=None,
            created_at=now,
            updated_at=now,
        )
        new_contract.content_hash = new_contract.compute_content_hash()
        return new_contract
