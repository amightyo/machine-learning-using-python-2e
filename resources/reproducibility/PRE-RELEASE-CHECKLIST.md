# Pre-Release Reproducibility Checklist

Use before creating a GitHub Release and Zenodo archive.

## Repository
- [ ] Working tree is clean.
- [ ] `main` contains all intended manuscript changes.
- [ ] Release commit SHA is recorded.
- [ ] Release tag is chosen but not yet archived.

## Environment
- [ ] Fresh virtual environment created.
- [ ] `environment/requirements-tested.txt` installs successfully.
- [ ] `python tools/verify_environment.py` passes.
- [ ] Quarto version recorded.
- [ ] Python version recorded.
- [ ] `python tools/snapshot_environment.py` executed.
- [ ] Snapshot committed before the final tag.

## Code
- [ ] `python tools/audit_book_code.py` passes.
- [ ] `python tools/audit_book_code.py --render` passes.
- [ ] No unresolved `DeprecationWarning`.
- [ ] No unresolved `FutureWarning`.
- [ ] No `n_jobs=-1` textbook examples.
- [ ] No weak `LOKY_MAX_CPU_COUNT` `setdefault()` usage.
- [ ] Random processes are seeded where deterministic repetition is intended.

## Render
- [ ] Full book renders from a clean environment.
- [ ] Figures appear.
- [ ] Tables appear.
- [ ] Equations render.
- [ ] Cross-references resolve.
- [ ] Search works.
- [ ] References render.
- [ ] No unexpected notebook tracebacks appear in output.

## Scholarly artifact
- [ ] `CITATION.cff` updated.
- [ ] Version and fixed publication date updated.
- [ ] DOI placeholder ready for final DOI.
- [ ] License files correct.
- [ ] README release status updated.
- [ ] Acknowledgments final.
- [ ] Preferred citation final.
- [ ] Environment snapshot included.

## Archive
- [ ] GitHub Release created from the final tag.
- [ ] Release archived in Zenodo.
- [ ] DOI resolves.
- [ ] DOI added back to the book metadata and README if needed.
- [ ] Final archival citation verified.
