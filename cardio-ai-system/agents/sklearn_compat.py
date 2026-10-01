"""Graceful degradation when a host security policy blocks sklearn's libsvm.

Why this exists
---------------
Some machines run an enterprise Application Control / WDAC policy that
blocks specific unsigned native extensions. On the reference laptop this
manifests as::

    ImportError: DLL load failed while importing _libsvm:
    An Application Control policy has blocked this file.

The file itself is genuine (its sha256 matches pip's ``RECORD`` for
scikit-learn 1.9.1) — the policy is reputation/signing based, not a
malware finding. But the block only affects ``sklearn.svm._libsvm`` /
``_libsvm_sparse``; every other scikit-learn extension loads, and the
import chain that reaches ``svm._base`` (via ``linear_model._logistic``)
is pulled in by *any* ``sklearn.ensemble`` import — i.e. merely unpickling
PulseIQ's RandomForest triggers it.

What this module does
---------------------
``ensure_sklearn_importable()`` probes the real extension once:

- If it imports (normal machines, or when a transient block has cleared),
  nothing changes — no shim is installed.
- If a host policy blocked it, inert placeholder modules are registered in
  ``sys.modules`` so the rest of scikit-learn imports. The blocked file is
  **never loaded or executed** — the security policy's intent is fully
  preserved; the application simply stops depending on that one file.

Safety properties
-----------------
- PulseIQ's screening model is a ``RandomForestClassifier`` — it never
  calls libsvm. Verified by unpickling and predicting under the shim.
- The placeholder raises a clear ``RuntimeError`` (PEP 562 ``__getattr__``)
  if anything ever *does* touch a libsvm symbol, so SVM-based estimators
  fail loudly instead of silently misbehaving.
- Narrow trigger: only ``ImportError`` on those two module names is
  tolerated; any other failure still propagates.
"""

from __future__ import annotations

import sys
import types

# The two extensions svm/_base.py imports unconditionally at module level.
_BLOCKED_MODULES = ("sklearn.svm._libsvm", "sklearn.svm._libsvm_sparse")

_warning_emitted = False


def _make_placeholder(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__doc__ = (
        f"Inert placeholder for {name}: the real extension is blocked by this "
        "machine's Application Control policy. It was never loaded."
    )

    def __getattr__(attr: str):
        raise RuntimeError(
            f"{name}.{attr} is unavailable: this machine's Application Control "
            "policy blocks scikit-learn's libsvm extension, so it was never "
            "loaded. PulseIQ's RandomForest screening model does not use "
            "libsvm; only SVM-based estimators would need it."
        )

    module.__getattr__ = __getattr__  # PEP 562
    return module


def ensure_sklearn_importable() -> bool:
    """Make ``sklearn.ensemble`` importable even under a libsvm block.

    Returns ``True`` when the real extension loaded (no shim needed) and
    ``False`` when the placeholder shim had to be installed.
    """
    global _warning_emitted
    try:
        import sklearn.svm._libsvm  # noqa: F401  — probe the real file
        return True
    except ImportError as exc:
        # Only tolerate a failure of THIS import; anything else propagates.
        if "libsvm" not in str(exc).lower() and "_libsvm" not in str(exc):
            raise
        reason = str(exc)
    for name in _BLOCKED_MODULES:
        if name not in sys.modules:
            sys.modules[name] = _make_placeholder(name)
    if not _warning_emitted:
        _warning_emitted = True
        print(
            "[pulseiq] WARNING: host Application Control policy blocks "
            "sklearn's libsvm extension; installed an inert placeholder "
            "(RandomForest inference is unaffected, SVM estimators would "
            f"raise a clear error). Block reason: {reason.splitlines()[0][:120]}"
        )
    return False
