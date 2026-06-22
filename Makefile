.PHONY: smoke master

smoke:
	python3 models/smoke_test.py

master:
	python3 models/build_master_output.py
