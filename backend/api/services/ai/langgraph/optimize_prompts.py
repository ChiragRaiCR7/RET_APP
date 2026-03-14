"""
Offline DSPy Prompt Optimization for RET v4 RAG Pipeline.

Runs a DSPy teleprompter (BootstrapFewShot or MIPRO) against the
evaluation dataset to produce optimised prompt parameters for the
query-transform and answer-generation modules.

Optimised prompts are serialised to JSON and can be loaded at startup
via ``load_optimised_modules()`` when ``FEATURE_DSPY_ENABLED`` is True.

Usage::

    # From backend directory:
    python -m api.services.ai.langgraph.optimize_prompts \\
        --eval-path eval/rag_cases.json \\
        --output-dir eval/optimised \\
        --strategy bootstrap

Requires:
    pip install "dspy-ai>=2.5.0"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )


def _configure_dspy() -> None:
    """Configure DSPy LM from RET settings."""
    from api.services.ai.langgraph.dspy_modules import configure_dspy_lm
    configure_dspy_lm()


# ===================================================================
# DSPy metric for evaluation
# ===================================================================


def _build_metric():
    """
    Build a DSPy-compatible metric function from RET evaluation scoring.

    DSPy metrics take (example, prediction, trace=None) and return
    a float score.
    """
    from api.services.ai.langgraph.evaluation import (
        EvalCase,
        _score_contains,
        _score_not_contains,
    )

    def metric(example, prediction, trace=None):
        """Score a DSPy prediction against expected outputs."""
        # Extract from DSPy example/prediction objects
        expected_contains = getattr(example, "expected_contains", [])
        expected_not_contains = getattr(example, "expected_not_contains", [])

        answer = ""
        if hasattr(prediction, "answer"):
            answer = prediction.answer or ""
        elif hasattr(prediction, "analysis_json"):
            answer = prediction.analysis_json or ""

        s1 = _score_contains(answer, expected_contains) if expected_contains else 1.0
        s2 = _score_not_contains(answer, expected_not_contains) if expected_not_contains else 1.0

        return (s1 * 0.7 + s2 * 0.3)

    return metric


# ===================================================================
# Build training examples from eval dataset
# ===================================================================


def _load_training_examples(eval_path: str):
    """Convert EvalDataset cases into DSPy Example objects."""
    try:
        import dspy  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("dspy-ai package required") from exc

    from api.services.ai.langgraph.evaluation import EvalDataset

    dataset = EvalDataset.load(eval_path)
    examples = []

    for case in dataset.cases:
        ex = dspy.Example(
            query=case.query,
            expected_contains=case.expected_answer_contains,
            expected_not_contains=case.expected_answer_not_contains,
            expected_intent=case.expected_intent or "factual",
        ).with_inputs("query")
        examples.append(ex)

    return examples


# ===================================================================
# Optimization strategies
# ===================================================================


def optimize_bootstrap(
    module,
    trainset: list,
    metric,
    *,
    max_bootstrapped_demos: int = 4,
    max_labeled_demos: int = 4,
) -> Any:
    """Run BootstrapFewShot optimization."""
    import dspy  # type: ignore[import-untyped]

    teleprompter = dspy.BootstrapFewShot(
        metric=metric,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_labeled_demos,
    )

    logger.info(
        "Starting BootstrapFewShot with %d examples (max_demos=%d)",
        len(trainset), max_bootstrapped_demos,
    )
    optimised = teleprompter.compile(module, trainset=trainset)
    return optimised


def optimize_mipro(
    module,
    trainset: list,
    metric,
    *,
    num_candidates: int = 5,
    num_trials: int = 10,
) -> Any:
    """Run MIPRO optimization (if available in dspy version)."""
    try:
        import dspy  # type: ignore[import-untyped]
        from dspy.teleprompt import MIPRO  # type: ignore[import-untyped]

        teleprompter = MIPRO(
            metric=metric,
            num_candidates=num_candidates,
            num_trials=num_trials,
        )

        logger.info(
            "Starting MIPRO with %d examples (candidates=%d, trials=%d)",
            len(trainset), num_candidates, num_trials,
        )
        optimised = teleprompter.compile(module, trainset=trainset)
        return optimised

    except ImportError:
        logger.warning("MIPRO not available in this dspy version, falling back to BootstrapFewShot")
        return optimize_bootstrap(module, trainset, metric)


# ===================================================================
# Save / Load optimised modules
# ===================================================================


def save_optimised_module(module, output_path: str | Path, name: str) -> Path:
    """Save an optimised DSPy module to disk."""
    p = Path(output_path) / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    module.save(str(p))
    logger.info("Saved optimised module: %s", p)
    return p


def load_optimised_modules(optimised_dir: str | Path) -> Dict[str, bool]:
    """
    Load optimised DSPy modules from disk and replace the module singletons.

    Returns a dict indicating which modules were loaded.
    """
    from api.services.ai.langgraph.dspy_modules import (
        configure_dspy_lm,
        get_query_transform_module,
        get_answer_generation_module,
        get_citation_repair_module,
    )

    configure_dspy_lm()
    loaded: Dict[str, bool] = {}
    base = Path(optimised_dir)

    for name, getter in [
        ("query_transform", get_query_transform_module),
        ("answer_generation", get_answer_generation_module),
        ("citation_repair", get_citation_repair_module),
    ]:
        path = base / f"{name}.json"
        if path.exists():
            try:
                mod = getter()
                mod._predict.load(str(path))
                loaded[name] = True
                logger.info("Loaded optimised %s from %s", name, path)
            except Exception as exc:
                logger.warning("Failed to load optimised %s: %s", name, exc)
                loaded[name] = False
        else:
            loaded[name] = False

    return loaded


# ===================================================================
# CLI entry-point
# ===================================================================


def main(argv: Optional[List[str]] = None) -> None:
    """Run offline DSPy prompt optimization."""
    _setup_logging()

    parser = argparse.ArgumentParser(description="RET v4 DSPy Prompt Optimization")
    parser.add_argument(
        "--eval-path",
        default="eval/rag_cases.json",
        help="Path to evaluation dataset JSON",
    )
    parser.add_argument(
        "--output-dir",
        default="eval/optimised",
        help="Directory to save optimised modules",
    )
    parser.add_argument(
        "--strategy",
        choices=["bootstrap", "mipro"],
        default="bootstrap",
        help="Optimization strategy",
    )
    parser.add_argument(
        "--max-demos",
        type=int,
        default=4,
        help="Max bootstrapped demos (bootstrap strategy)",
    )
    parser.add_argument(
        "--module",
        choices=["query_transform", "answer_generation", "all"],
        default="all",
        help="Which module(s) to optimize",
    )
    args = parser.parse_args(argv)

    # Configure DSPy with Azure OpenAI
    _configure_dspy()

    # Load training data
    trainset = _load_training_examples(args.eval_path)
    if not trainset:
        logger.error("No training examples found in %s", args.eval_path)
        sys.exit(1)

    metric = _build_metric()
    optimize_fn = optimize_mipro if args.strategy == "mipro" else optimize_bootstrap

    results: Dict[str, str] = {}
    optimize_kwargs: Dict[str, Any] = {}
    if args.strategy == "bootstrap":
        optimize_kwargs["max_bootstrapped_demos"] = args.max_demos
    elif args.strategy == "mipro":
        optimize_kwargs["num_candidates"] = args.max_demos

    if args.module in ("query_transform", "all"):
        logger.info("=== Optimising QueryTransformModule ===")
        from api.services.ai.langgraph.dspy_modules import get_query_transform_module
        mod = get_query_transform_module()
        optimised = optimize_fn(mod._predict, trainset, metric, **optimize_kwargs)
        path = save_optimised_module(optimised, args.output_dir, "query_transform")
        results["query_transform"] = str(path)

    if args.module in ("answer_generation", "all"):
        logger.info("=== Optimising AnswerGenerationModule ===")
        from api.services.ai.langgraph.dspy_modules import get_answer_generation_module
        mod = get_answer_generation_module()
        optimised = optimize_fn(mod._predict, trainset, metric, **optimize_kwargs)
        path = save_optimised_module(optimised, args.output_dir, "answer_generation")
        results["answer_generation"] = str(path)

    logger.info("Optimization complete. Results: %s", json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
