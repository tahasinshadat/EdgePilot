# Makefile
.PHONY: setup dev api ui mcp test lint clean

setup:
	python -m pip install --upgrade pip
	pip install -e .

dev:
	uvicorn edgepilot.api.main:app --reload --host 127.0.0.1 --port 8000

api:
	uvicorn edgepilot.api.main:app --host 127.0.0.1 --port 8000

ui:
	streamlit run edgepilot/ui/app.py --server.port 8501

mcp:
	edgepilot mcp

test:
	pytest -q

lint:
	python -m compileall edgepilot

clean:
	rm -rf build dist *.egg-info .pytest_cache
