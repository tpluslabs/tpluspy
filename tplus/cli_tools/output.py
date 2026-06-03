import json
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from tplus.model.chain_address import ChainAddress

PAGER_THRESHOLD = 10


def chain_address_record(chain_addr: "ChainAddress") -> dict:
    """Structured view of a ChainAddress with the chain id split into routing_id/vm_id."""
    chain_id = chain_addr.chain_id
    return {
        "address": chain_addr.address,
        "routing_id": chain_id.routing_id,
        "vm_id": chain_id.vm_id,
    }


def echo_with_pager(
    items: list[str],
    *,
    no_pager: bool = False,
    threshold: int = PAGER_THRESHOLD,
    sep: str = "\n",
) -> None:
    """Echo ITEMS; page through $PAGER when len(items) >= threshold and not NO_PAGER."""
    if not items:
        return

    if no_pager or len(items) < threshold:
        for item in items:
            click.echo(item)
        return

    click.echo_via_pager(sep.join(items))


def render(
    records: list[dict],
    output_format: str = "table",
    *,
    no_pager: bool = False,
    threshold: int = PAGER_THRESHOLD,
) -> None:
    """Emit records as a table (default) or JSON, paging when len(records) >= threshold."""
    text = _render_text(records, output_format)
    if not no_pager and len(records) >= threshold:
        click.echo_via_pager(text)
        return

    click.echo(text)


def _render_text(records: list[dict], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(records, indent=2, default=str)

    if not records:
        return "(empty)"

    headers = list(records[0].keys())

    if len(headers) > 5:
        # Wide records: render one labeled block per record.
        blocks = []
        for rec in records:
            keys = list(rec.keys())
            label_key, label_val = keys[0], rec[keys[0]]
            lines = [f"{label_key}={label_val}"]
            inner = keys[1:]
            kw = max((len(k) for k in inner), default=0)
            for k in inner:
                lines.append(f"  {k.ljust(kw)}  {_fmt(rec[k])}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    rows = [[_fmt(r.get(h, "")) for h in headers] for r in records]
    widths = [
        max(len(str(h)), *(len(rows[r][i]) for r in range(len(rows))))
        for i, h in enumerate(headers)
    ]
    sep = "  "
    lines = [sep.join(str(h).ljust(w) for h, w in zip(headers, widths, strict=False))]
    lines.append(sep.join("-" * w for w in widths))
    for row in rows:
        lines.append(sep.join(c.ljust(w) for c, w in zip(row, widths, strict=False)))
    return "\n".join(lines)


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list | tuple):
        return ",".join(_fmt(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, default=str)
    return str(v)
