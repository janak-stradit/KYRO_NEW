"""
Validation & test suite for the AML data generator.

Tests:
  - Customer schema completeness
  - Account schema completeness
  - Transaction schema completeness
  - Referential integrity (customer_id / account_id links)
  - Risk score / risk level consistency
  - Correct data types for all columns
  - Flask API health, stats, single-customer, generate endpoints
  - Excel download endpoint (byte-level check)
"""

import sys
import os
import json
import time
import unittest
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator.data_generator import (
    generate_customer,
    generate_accounts,
    generate_transactions,
    generate_dataset,
)
from generator.excel_writer import build_workbook, workbook_to_bytes

# ─────────────────────────────────────────────
# Expected columns (from Data_Dictionary sheet)
# ─────────────────────────────────────────────
CUSTOMER_REQUIRED_KEYS = [
    "customer_id", "full_name", "email", "phone", "date_of_birth",
    "country", "residency_country", "kyc_status", "kyc_last_review",
    "pep_flag", "sanctions_flag", "adverse_media_flag", "risk_level",
    "risk_score", "customer_type", "customer_metadata",
]

ACCOUNT_REQUIRED_KEYS = [
    "account_id", "customer_id", "account_type", "account_status",
    "currency", "balance", "opened_date", "account_metadata",
]

TRANSACTION_REQUIRED_KEYS = [
    "transaction_id", "customer_id", "account_id", "transaction_date",
    "transaction_type", "amount", "currency", "risk_flags",
    "source_system", "meta_counterparty", "meta_counterparty_type",
    "meta_location", "meta_country", "meta_country_code",
    "meta_destination_country", "meta_origin_country", "meta_source",
]


class TestCustomerGenerator(unittest.TestCase):
    def setUp(self):
        self.customer = generate_customer(1)

    def test_all_keys_present(self):
        for key in CUSTOMER_REQUIRED_KEYS:
            self.assertIn(key, self.customer, f"Missing key: {key}")

    def test_customer_id_format(self):
        self.assertTrue(self.customer["customer_id"].startswith("CUST-"))

    def test_risk_score_range(self):
        self.assertGreaterEqual(self.customer["risk_score"], 0.0)
        self.assertLessEqual(self.customer["risk_score"], 100.0)

    def test_risk_level_matches_score(self):
        score = self.customer["risk_score"]
        level = self.customer["risk_level"]
        if score >= 75:
            self.assertEqual(level, "CRITICAL")
        elif score >= 50:
            self.assertEqual(level, "HIGH")
        elif score >= 25:
            self.assertEqual(level, "MEDIUM")
        else:
            self.assertEqual(level, "LOW")

    def test_boolean_fields(self):
        self.assertIsInstance(self.customer["pep_flag"], bool)
        self.assertIsInstance(self.customer["sanctions_flag"], bool)
        self.assertIsInstance(self.customer["adverse_media_flag"], bool)

    def test_kyc_status_valid(self):
        self.assertIn(self.customer["kyc_status"], ["COMPLETE", "PENDING", "EXPIRED", "PARTIAL"])

    def test_customer_type_valid(self):
        self.assertIn(self.customer["customer_type"], ["INDIVIDUAL", "CORPORATE", "PARTNERSHIP", "TRUST", "NGO"])

    def test_16_columns(self):
        self.assertEqual(len(self.customer), 16)


class TestAccountGenerator(unittest.TestCase):
    def setUp(self):
        customer = generate_customer(1)
        self.cid = customer["customer_id"]
        self.accounts = generate_accounts(self.cid)

    def test_at_least_one_account(self):
        self.assertGreaterEqual(len(self.accounts), 1)

    def test_max_5_accounts(self):
        self.assertLessEqual(len(self.accounts), 5)

    def test_all_keys_present(self):
        for acc in self.accounts:
            for key in ACCOUNT_REQUIRED_KEYS:
                self.assertIn(key, acc, f"Missing key: {key}")

    def test_account_id_format(self):
        for acc in self.accounts:
            self.assertTrue(acc["account_id"].startswith("ACC-"))

    def test_customer_id_linked(self):
        for acc in self.accounts:
            self.assertEqual(acc["customer_id"], self.cid)

    def test_balance_is_float(self):
        for acc in self.accounts:
            self.assertIsInstance(acc["balance"], float)

    def test_account_status_valid(self):
        valid = {"ACTIVE", "CLOSED", "FROZEN", "SUSPENDED"}
        for acc in self.accounts:
            self.assertIn(acc["account_status"], valid)

    def test_8_columns(self):
        for acc in self.accounts:
            self.assertEqual(len(acc), 8)


class TestTransactionGenerator(unittest.TestCase):
    def setUp(self):
        customer = generate_customer(1)
        self.cid = customer["customer_id"]
        accounts = generate_accounts(self.cid)
        self.acc_id = accounts[0]["account_id"]
        self.transactions = generate_transactions(self.cid, self.acc_id)

    def test_at_least_50_transactions(self):
        self.assertGreaterEqual(len(self.transactions), 50)

    def test_max_200_transactions(self):
        self.assertLessEqual(len(self.transactions), 200)

    def test_all_keys_present(self):
        for txn in self.transactions[:5]:
            for key in TRANSACTION_REQUIRED_KEYS:
                self.assertIn(key, txn, f"Missing key: {key}")

    def test_customer_id_linked(self):
        for txn in self.transactions:
            self.assertEqual(txn["customer_id"], self.cid)

    def test_account_id_linked(self):
        for txn in self.transactions:
            self.assertEqual(txn["account_id"], self.acc_id)

    def test_amount_positive(self):
        for txn in self.transactions:
            self.assertGreater(txn["amount"], 0)

    def test_transaction_id_unique(self):
        ids = [txn["transaction_id"] for txn in self.transactions]
        self.assertEqual(len(ids), len(set(ids)))

    def test_17_columns(self):
        for txn in self.transactions[:5]:
            self.assertEqual(len(txn), 17)


class TestDatasetReferentialIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = generate_dataset(num_customers=10)

    def test_customer_count(self):
        self.assertEqual(len(self.dataset["customers"]), 10)

    def test_all_accounts_have_valid_customer_ids(self):
        valid_cids = {c["customer_id"] for c in self.dataset["customers"]}
        for acc in self.dataset["accounts"]:
            self.assertIn(acc["customer_id"], valid_cids)

    def test_all_transactions_have_valid_customer_ids(self):
        valid_cids = {c["customer_id"] for c in self.dataset["customers"]}
        for txn in self.dataset["transactions"]:
            self.assertIn(txn["customer_id"], valid_cids)

    def test_all_transactions_have_valid_account_ids(self):
        valid_aids = {a["account_id"] for a in self.dataset["accounts"]}
        for txn in self.dataset["transactions"]:
            self.assertIn(txn["account_id"], valid_aids)

    def test_every_customer_has_at_least_one_account(self):
        cids_with_accounts = {a["customer_id"] for a in self.dataset["accounts"]}
        for c in self.dataset["customers"]:
            self.assertIn(c["customer_id"], cids_with_accounts)

    def test_every_account_has_transactions(self):
        aids_with_txns = {t["account_id"] for t in self.dataset["transactions"]}
        for a in self.dataset["accounts"]:
            self.assertIn(a["account_id"], aids_with_txns)


class TestExcelWriter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = generate_dataset(num_customers=5)
        cls.wb = build_workbook(cls.dataset)
        cls.wb_bytes = workbook_to_bytes(cls.wb)

    def test_returns_bytes(self):
        self.assertIsInstance(self.wb_bytes, bytes)

    def test_bytes_non_empty(self):
        self.assertGreater(len(self.wb_bytes), 0)

    def test_four_sheets_exist(self):
        self.assertIn("Customer", self.wb.sheetnames)
        self.assertIn("Accounts", self.wb.sheetnames)
        self.assertIn("Transactions", self.wb.sheetnames)
        self.assertIn("Data_Dictionary", self.wb.sheetnames)

    def test_customer_row_count(self):
        ws = self.wb["Customer"]
        # 1 header + 5 customer rows = 6
        self.assertEqual(ws.max_row, 6)

    def test_account_row_count(self):
        ws = self.wb["Accounts"]
        expected = len(self.dataset["accounts"]) + 1  # +1 for header
        self.assertEqual(ws.max_row, expected)

    def test_transaction_row_count(self):
        ws = self.wb["Transactions"]
        expected = len(self.dataset["transactions"]) + 1
        self.assertEqual(ws.max_row, expected)

    def test_customer_column_headers(self):
        ws = self.wb["Customer"]
        headers = [ws.cell(1, col).value for col in range(1, 17)]
        self.assertIn("customer_id", headers)
        self.assertIn("risk_score", headers)
        self.assertIn("customer_metadata", headers)

    def test_transaction_column_count(self):
        ws = self.wb["Transactions"]
        self.assertEqual(ws.max_column, 17)

    def test_data_dictionary_row_count(self):
        ws = self.wb["Data_Dictionary"]
        self.assertEqual(ws.max_row, 42)  # 1 header + 41 entries


class TestFlaskAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Start Flask in a background thread."""
        import generator_service as flask_app
        flask_app.app.config["TESTING"] = True
        cls.client = flask_app.app.test_client()

    def test_health_endpoint(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["status"], "ok")

    def test_stats_endpoint_default(self):
        r = self.client.get("/api/stats")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["requested_customers"], 5000)

    def test_stats_endpoint_custom(self):
        r = self.client.get("/api/stats?customers=100")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["requested_customers"], 100)

    def test_single_customer_endpoint(self):
        r = self.client.post(
            "/api/generate/single-customer",
            json={"customer_index": 42},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("customer", data)
        self.assertIn("accounts", data)
        self.assertIn("transactions", data)
        self.assertGreaterEqual(data["summary"]["num_accounts"], 1)
        self.assertGreaterEqual(data["summary"]["num_transactions"], 50)

    def test_generate_endpoint_small(self):
        r = self.client.post(
            "/api/generate",
            json={"num_customers": 3},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["meta"]["num_customers"], 3)
        self.assertGreaterEqual(data["meta"]["num_accounts"], 3)
        self.assertGreaterEqual(data["meta"]["num_transactions"], 150)
        self.assertIn("data", data)
        self.assertIn("customers", data["data"])
        self.assertIn("accounts", data["data"])
        self.assertIn("transactions", data["data"])

    def test_generate_invalid_customer_count_too_high(self):
        r = self.client.post(
            "/api/generate",
            json={"num_customers": 99999},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_generate_invalid_customer_count_zero(self):
        r = self.client.post(
            "/api/generate",
            json={"num_customers": 0},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_download_endpoint_small(self):
        r = self.client.post(
            "/api/generate/download",
            json={"num_customers": 2, "save_to_disk": False},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn(
            "spreadsheetml",
            r.content_type,
        )
        self.assertGreater(len(r.data), 1000)


if __name__ == "__main__":
    print("=" * 60)
    print("  KYRO AML Data Generator — Full Validation Suite")
    print("=" * 60)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Order matters for output readability
    suite.addTests(loader.loadTestsFromTestCase(TestCustomerGenerator))
    suite.addTests(loader.loadTestsFromTestCase(TestAccountGenerator))
    suite.addTests(loader.loadTestsFromTestCase(TestTransactionGenerator))
    suite.addTests(loader.loadTestsFromTestCase(TestDatasetReferentialIntegrity))
    suite.addTests(loader.loadTestsFromTestCase(TestExcelWriter))
    suite.addTests(loader.loadTestsFromTestCase(TestFlaskAPI))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
