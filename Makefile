.PHONY: help docs-gates cross-repo-agent

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "%-20s %s\n", $$1, $$2}'

# The five documentation gates also listed in AGENTS.md. Each detector runs its
# --selftest first, because a gate that cannot fail is the same as no gate.
docs-gates: ## Run the documentation gates (naming, number parity, headings, detector mutations, writing style)
	python3 scripts/check-fsx-naming.py --selftest
	python3 scripts/check-fsx-naming.py
	python3 scripts/check-doc-number-parity.py --selftest
	python3 scripts/check-doc-number-parity.py
	python3 scripts/check-heading-style.py --selftest
	python3 scripts/check-heading-style.py
	python3 scripts/check-detector-mutations.py
	python3 scripts/ai_style_rules.py docs/ --fail

# Called by a local supervisor script that runs each repository's gates. Do not call that
# script from here: it calls this target, so doing both recurses until the timeout.
cross-repo-agent: docs-gates ## Run the gates for the Kiro Bot supervisor (no recursion)
	@mkdir -p docs/agent/notifications
	@echo "cross-repo-agent: gates passed."
