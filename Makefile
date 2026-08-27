.PHONY: setup gen demo test bench lint clean

setup:            ## create venv and install dependencies
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

gen:              ## generate the synthetic dataset + ground truth
	.venv/bin/python -m datagen.build

demo:             ## run the API and serve the console
	.venv/bin/uvicorn api.main:app --reload --port 8000

test:             ## run the test suite (includes the invariant tests)
	.venv/bin/pytest -q

bench:            ## run the benchmark harness and print the report
	.venv/bin/python -m bench.run --report

lint:
	.venv/bin/ruff check .

clean:
	rm -rf data/warehouse/*.duckdb .pytest_cache __pycache__
