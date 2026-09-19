# SPDX-License-Identifier: Apache-2.0
# Synthetic public status API; no credentials, database, or paid services.

from flask import Flask, jsonify

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/info")
def info():
    return jsonify({"service": "status-api", "version": 1, "read_only": True})
