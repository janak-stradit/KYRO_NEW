"""
Flask API for AML synthetic data generation.

Endpoints:
  POST /api/generate          - Generate dataset (JSON response)
  POST /api/generate/download  - Generate dataset and return XLSX file
  GET  /api/health            - Health check
  GET  /api/stats             - Returns expected stats for N customers
"""

import os
import json
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import io

from generator.data_generator import generate_dataset, generate_customer, generate_accounts, generate_transactions
from generator.excel_writer import build_workbook, workbook_to_bytes

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "KYRO AML Data Generator",
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }), 200


@app.route("/api/stats", methods=["GET"])
def stats():
    """Return estimated row counts for a given number of customers."""
    n = int(request.args.get("customers", 5000))
    avg_accounts_per_customer = 3       # random 1-5
    avg_txns_per_account = 125          # random 50-200
    return jsonify({
        "requested_customers": n,
        "estimated_accounts": n * avg_accounts_per_customer,
        "estimated_transactions": n * avg_accounts_per_customer * avg_txns_per_account,
    }), 200


@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Generate a dataset and return it as JSON.

    Body (optional JSON):
        { "num_customers": 5000 }
    """
    body = request.get_json(silent=True) or {}
    num_customers = int(body.get("num_customers", 5000))

    if num_customers < 1 or num_customers > 10000:
        return jsonify({"error": "num_customers must be between 1 and 10000"}), 400

    logger.info(f"Generating dataset for {num_customers} customers ...")
    start = datetime.now(timezone.utc).replace(tzinfo=None)
    dataset = generate_dataset(num_customers)
    elapsed = (datetime.now(timezone.utc).replace(tzinfo=None) - start).total_seconds()

    logger.info(
        f"Done in {elapsed:.1f}s — "
        f"customers={len(dataset['customers'])}, "
        f"accounts={len(dataset['accounts'])}, "
        f"transactions={len(dataset['transactions'])}"
    )

    return jsonify({
        "meta": {
            "num_customers": len(dataset["customers"]),
            "num_accounts": len(dataset["accounts"]),
            "num_transactions": len(dataset["transactions"]),
            "generation_time_seconds": round(elapsed, 2),
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        },
        "data": dataset,
    }), 200


@app.route("/api/generate/download", methods=["POST"])
def generate_and_download():
    """
    Generate a dataset and return it as a downloadable XLSX file.

    Body (optional JSON):
        { "num_customers": 5000, "save_to_disk": false }
    """
    body = request.get_json(silent=True) or {}
    num_customers = int(body.get("num_customers", 5000))
    save_to_disk = bool(body.get("save_to_disk", True))

    if num_customers < 1 or num_customers > 10000:
        return jsonify({"error": "num_customers must be between 1 and 10000"}), 400

    logger.info(f"Generating XLSX for {num_customers} customers ...")
    start = datetime.now(timezone.utc).replace(tzinfo=None)
    dataset = generate_dataset(num_customers)
    elapsed = (datetime.now(timezone.utc).replace(tzinfo=None) - start).total_seconds()
    logger.info(f"Dataset built in {elapsed:.1f}s, writing Excel ...")

    wb = build_workbook(dataset)
    file_bytes = workbook_to_bytes(wb)

    timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
    filename = f"aml_dataset_{num_customers}_customers_{timestamp}.xlsx"

    if save_to_disk:
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "wb") as f:
            f.write(file_bytes)
        logger.info(f"Saved to {path}")

    return send_file(
        io.BytesIO(file_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/generate/single-customer", methods=["POST"])
def generate_single_customer():
    """
    Generate a single customer with their accounts and transactions.
    Useful for quick testing.

    Body (optional JSON):
        { "customer_index": 1 }
    """
    body = request.get_json(silent=True) or {}
    idx = int(body.get("customer_index", 1))

    customer = generate_customer(idx)
    accounts = generate_accounts(customer["customer_id"])
    transactions = []
    for acc in accounts:
        txns = generate_transactions(customer["customer_id"], acc["account_id"])
        transactions.extend(txns)

    return jsonify({
        "customer": customer,
        "accounts": accounts,
        "transactions": transactions,
        "summary": {
            "num_accounts": len(accounts),
            "num_transactions": len(transactions),
        },
    }), 200


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    logger.info(f"Starting KYRO AML Data Generator API on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
