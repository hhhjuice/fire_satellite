"""Shared math utilities for Bayesian logit confidence fusion."""
import math


def logit(p: float) -> float:
    """Log-odds of probability p. Clamps to avoid ±infinity."""
    p = max(1e-9, min(1 - 1e-9, p))
    return math.log(p / (1.0 - p))


def sigmoid(x: float) -> float:
    """Sigmoid function. Clamps input to avoid overflow."""
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))
