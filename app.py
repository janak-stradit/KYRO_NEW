"""
Flask API — AML synthetic data generation service.

Endpoints
---------
GET  /api/health                  liveness probe
GET  /api/stats?customers=N       estimated row counts
POST /api/generate                JSON dataset
POST /api/generate/single-customer  single customer preview
POST /api/generate/download       XLSX file download
"""

import io
import os
import logging
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from generator.data_generator import (
    generate_customer,
    generate_accounts,
    generate_transactions,
    generate_dataset,
)
from generator.excel_writer import build_workbook, workbook_to_bytes

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "AML Data Generator",
        "ts": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/stats")
def stats():
    n = int(request.args.get("customers", 5000))
    # rough averages: 3 accounts/customer, 125 txns/account
    return jsonify({
        "requested_customers": n,
        "estimated_accounts": n * 3,
        "estimated_transactions": n * 3 * 125,
    })


@app.route("/api/generate", methods=["POST"])
def generate():
    body = request.get_json(silent=True) or {}
    n = int(body.get("num_customers", 5000))

    if not 1 <= n <= 10000:
        return jsonify({"error": "num_customers must be between 1 and 10000"}), 400

    log.info("generating dataset: n=%d", n)
    t0 = datetime.now(timezone.utc)
    data = generate_dataset(n)
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    log.info("done in %.1fs — customers=%d accounts=%d transactions=%d",
             elapsed, len(data["customers"]), len(data["accounts"]), len(data["transactions"]))

    return jsonify({
        "meta": {
            "num_customers": len(data["customers"]),
            "num_accounts": len(data["accounts"]),
            "num_transactions": len(data["transactions"]),
            "generation_time_seconds": round(elapsed, 2),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "data": data,
    })


@app.route("/api/generate/single-customer", methods=["POST"])
def single_customer():
    body = request.get_json(silent=True) or {}
    idx = int(body.get("customer_index", 1))

    customer = generate_customer(idx)
    accounts = generate_accounts(customer["customer_id"])
    transactions = []
    for acc in accounts:
        transactions.extend(generate_transactions(customer["customer_id"], acc["account_id"]))

    return jsonify({
        "customer": customer,
        "accounts": accounts,
        "transactions": transactions,
        "summary": {
            "num_accounts": len(accounts),
            "num_transactions": len(transactions),
        },
    })


@app.route("/api/generate/download", methods=["POST"])
def download():
    body = request.get_json(silent=True) or {}
    n = int(body.get("num_customers", 5000))
    save = bool(body.get("save_to_disk", True))

    if not 1 <= n <= 10000:
        return jsonify({"error": "num_customers must be between 1 and 10000"}), 400

    log.info("generating XLSX: n=%d", n)
    data = generate_dataset(n)
    wb = build_workbook(data)
    file_bytes = workbook_to_bytes(wb)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"aml_dataset_{n}c_{ts}.xlsx"

    if save:
        path = os.path.join(OUTPUT_DIR, fname)
        with open(path, "wb") as f:
            f.write(file_bytes)
        log.info("saved to %s", path)

    return send_file(
        io.BytesIO(file_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=fname,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
