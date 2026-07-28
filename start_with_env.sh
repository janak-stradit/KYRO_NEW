#!/bin/bash
set -a
source .env
set +a
exec venv/bin/python start_server.py
