# Contributing

The range grows by real contributions: new attack scenarios, new memory-backend
adapters, better detectors, repair improvements. This file shows what a complete
submission looks like, using the shipped A5 (retrieval flooding) scenario as the
worked example.

## Ground rules

- Synthetic targets only. Never point anything in here at a system you do not own.
- The scripted agent and the owner policy are the fixed defender. Attack
  contributions change neither; defense fixes are a separate track.
- Every attack scenario must show all three runs, with tests: the naive agent
  flips, the defended agent holds, and `repair()` restores the baseline.
- A documented known failure is a valid contribution. Label it as one; do not
  force the suite green by weakening an assertion.
- New dependencies stay optional and offline-capable, same as the `chroma` extra.

## Adding an attack scenario today

A5 is the reference for every place a new scenario must register. The tests and
the aggregate scoreboard iterate `SCENARIOS`, but four spots still need the new
id by hand (a starter issue tracks making this single-point):

1. The scenario entry itself in `SCENARIOS` in `mpolab/scenarios.py` - `name`,
   `attack_class`, `writes`, `poison_steps`, `compact`. A5's entry shows the shape.
2. The display-order tuple at the bottom of the same file.
3. The deep-link list in `scripts/build_demo.py`, then re-run
   `python scripts/build_demo.py` so `demo/index.html` picks the scenario up.
4. The expected aggregate in `tests/test_lab.py`
   (`test_aggregate_matches_scenario_outcomes`) and the scoreboard numbers in
   `README.md`.

A5's evidence, all asserted in the suite: the naive agent's recall window (k=10)
contains none of the owner's writes, only the ten flood writes, and its decision
flips to the attacker vendor. With defenses on, write-time screening quarantines
all ten flood writes (they carry a preference signal), so the owner policy stays
in the window; had any flood write slipped through, the origin policy would still
refuse it, degrading the decision to the built-in default rather than the
attacker's vendor. `repair()` removes all ten and restores the baseline.

## Adding a memory backend

Implement the contract from `mpolab/adapters.py` - retain / recall / compact /
delete / repair - over your stack (mem0, Zep, Letta, pgvector). The conformance
contract and every registered scenario in `tests/test_adapters.py` then run
against it. Keep the extra optional: the suite must skip cleanly when the
package is absent.

## Running the tests

```
pip install .            # or: pip install ".[chroma]" for the vector-store leg
python -m unittest discover -s tests -v
```

22 tests run on the standard library alone; 3 more run when chromadb is
installed (its default ONNX embedding model downloads once, about 80 MB, then
runs offline). Pull requests run both legs in CI.
