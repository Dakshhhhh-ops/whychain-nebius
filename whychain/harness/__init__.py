"""Pick the data harness. The local DuckDB harness is the default; Zetaris is an optional adapter (WHYCHAIN_HARNESS=zetaris)."""
from __future__ import annotations

from whychain.config import SETTINGS
from whychain.harness.base import DataHarness, QueryResult, TableInfo, catalog_text  # noqa: F401


def get_harness(prefer: str | None = None, allow_fallback: bool = True,
                dataset: str | None = None) -> tuple[DataHarness, list[str]]:
    """Return (harness, notes). Notes explain any fallback so the UI can show it."""
    prefer = (prefer or SETTINGS.harness).lower()
    notes: list[str] = []

    from whychain.harness.zetaris import configured

    if prefer == "zetaris" and not configured():
        notes.append("Zetaris selected but neither ZETARIS_USER (local platform) nor ZETARIS_API_KEY (cloud) is set; "
                     "using local fallback.")
    elif prefer == "zetaris":
        from whychain.harness.zetaris import ZetarisHarness

        z = ZetarisHarness(dataset=dataset)
        st = z.status()
        if st["ok"]:
            return z, notes
        notes.append(f"Zetaris unreachable at {st.get('url')} ({st.get('error', '')}); using local fallback.")
        if not allow_fallback:
            raise RuntimeError(notes[-1])
    from whychain.harness.local import LocalHarness

    # USE_POSTGRES=false: read the order system from its CSV export without trying Postgres (containers, demos)
    from whychain.config import env

    h = LocalHarness(dataset, use_postgres=env("USE_POSTGRES", "auto").lower() != "false")
    notes.append(f"Local DuckDB harness (ERP from {h.erp_mode}).")
    return h, notes
