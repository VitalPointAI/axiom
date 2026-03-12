"""Test scaffolds for spam transaction detection.

Covers spam detection logic: dust-amount filtering, known spam contract lists,
user-initiated tagging, and global rule propagation.

All test methods are pending stubs that will be implemented in plan 03-02.
They are marked with pytest.skip() so they are visible in the test collection
output but do not fail.
"""

import pytest


class TestSpamDetection:
    """Core spam detection: dust amounts and known contract addresses."""

    def test_dust_amount_flagged(self):
        """Transaction with amount below dust_threshold -> classified as Spam."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_known_spam_contract(self):
        """Transaction from address matching spam_rules.contract_address -> Spam."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_legitimate_not_flagged(self):
        """Normal-value transaction from unlisted address -> not Spam."""
        pytest.skip("Pending implementation in plan 03-02")


class TestSpamLearning:
    """User-driven spam learning and global propagation."""

    def test_user_tag_creates_rule(self):
        """User marking tx as spam creates a new spam_rules row for that contract."""
        pytest.skip("Pending implementation in plan 03-02")

    def test_global_propagation(self):
        """Global spam rule (user_id=NULL) is applied to all users during detection."""
        pytest.skip("Pending implementation in plan 03-02")
