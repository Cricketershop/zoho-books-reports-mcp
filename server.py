                amount = float(li.get("rate") or 0) * quantity
            amount = float(amount or 0)

            row = agg[key]
            row["sku"] = sku
            row["item_id"] = item_id
            row["item_name"] = name

            if is_return:
                row["return_quantity"] += quantity
                row["return_value"] += amount
            else:
                row["gross_quantity"] += quantity
                row["gross_sales"] += amount
            seen.add(key)

    invoice_detail_errors = 0
    for payload in invoice_details:
        if not payload:
            invoice_detail_errors += 1
            continue
        inv = payload.get("invoice") or payload
        seen: set[str] = set()
        add_lines(inv.get("line_items") or [], False, seen)
        for key in seen:
            agg[key]["invoice_count"] += 1

    # 2) Optionally subtract credit-note line items for net sales/quantity.
    credit_note_detail_errors = 0
    credit_notes: list[dict[str, Any]] = []
    if include_credit_notes:
        # Zoho's credit-note list endpoint does not consistently expose date-range
        # query params, so page through and filter locally by date.
        all_credit_notes = await _paged_zoho_get("creditnotes", {"sort_column": "date"})
        credit_notes = [
            x for x in all_credit_notes
            if x.get("status") != "void"
            and date_start <= str(x.get("date") or "") <= date_end
            and x.get("creditnote_id")
        ]

        credit_details = await _get_many_details(
            "creditnotes",
            [str(x["creditnote_id"]) for x in credit_notes],
            concurrency=20,
        )

        for payload in credit_details:
            if not payload:
                credit_note_detail_errors += 1
                continue
            cn = payload.get("creditnote") or payload
            seen: set[str] = set()
            add_lines(cn.get("line_items") or [], True, seen)
            for key in seen:
                agg[key]["credit_note_count"] += 1

    rows: list[dict[str, Any]] = []
    for row in agg.values():
        row["gross_quantity"] = round(row["gross_quantity"], 3)
        row["gross_sales"] = round(row["gross_sales"], 2)
        row["return_quantity"] = round(row["return_quantity"], 3)
        row["return_value"] = round(row["return_value"], 2)
        row["net_quantity"] = round(row["gross_quantity"] - row["return_quantity"], 3)
        row["net_sales"] = round(row["gross_sales"] - row["return_value"], 2)
        rows.append(row)

    rows.sort(key=lambda x: float(x.get(sort_by) or 0), reverse=True)
    top_n = max(1, min(int(top_n), 200))

    return {
        "date_start": date_start,
        "date_end": date_end,
        "sort_by": sort_by,
        "include_credit_notes": include_credit_notes,
        "invoice_count": len(invoices),
        "credit_note_count": len(credit_notes),
        "invoice_detail_errors": invoice_detail_errors,
        "credit_note_detail_errors": credit_note_detail_errors,
        "items_count": len(rows),
        "items": rows[:top_n],
    }


@mcp.tool()
async def zoho_books_read(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Advanced read-only Zoho Books GET tool for endpoints not yet wrapped above.
    Pass a relative Books v3 path such as 'reports/...' or 'items'.
    This tool never sends POST/PUT/PATCH/DELETE requests.
    """
    if not path or path.startswith("/"):
        path = path.lstrip("/")
    blocked = ("settings/preferences",)
    if any(path.startswith(x) for x in blocked):
        raise ValueError("This endpoint is blocked in the read-only connector")
    return await _zoho_get(path, params)


security = TransportSecuritySettings(
    allowed_hosts=[ALLOWED_HOST, f"{ALLOWED_HOST}:*", "localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"],
    allowed_origins=[f"https://{ALLOWED_HOST}", f"http://{ALLOWED_HOST}", "http://localhost", "http://127.0.0.1"],
)

app = mcp.streamable_http_app(
    transport_security=security,
    json_response=True,
)
                amount = float(li.get("rate") or 0) * quantity
            amount = float(amount or 0)

            row = agg[key]
            row["sku"] = sku
            row["item_id"] = item_id
            row["item_name"] = name

            if is_return:
                row["return_quantity"] += quantity
                row["return_value"] += amount
            else:
                row["gross_quantity"] += quantity
                row["gross_sales"] += amount
            seen.add(key)

    invoice_detail_errors = 0
    for payload in invoice_details:
        if not payload:
            invoice_detail_errors += 1
            continue
        inv = payload.get("invoice") or payload
        seen: set[str] = set()
        add_lines(inv.get("line_items") or [], False, seen)
        for key in seen:
            agg[key]["invoice_count"] += 1

    # 2) Optionally subtract credit-note line items for net sales/quantity.
    credit_note_detail_errors = 0
    credit_notes: list[dict[str, Any]] = []
    if include_credit_notes:
        # Zoho's credit-note list endpoint does not consistently expose date-range
        # query params, so page through and filter locally by date.
        all_credit_notes = await _paged_zoho_get("creditnotes", {"sort_column": "date"})
        credit_notes = [
            x for x in all_credit_notes
            if x.get("status") != "void"
            and date_start <= str(x.get("date") or "") <= date_end
            and x.get("creditnote_id")
        ]

        credit_details = await _get_many_details(
            "creditnotes",
            [str(x["creditnote_id"]) for x in credit_notes],
            concurrency=20,
        )

        for payload in credit_details:
            if not payload:
                credit_note_detail_errors += 1
                continue
            cn = payload.get("creditnote") or payload
            seen: set[str] = set()
            add_lines(cn.get("line_items") or [], True, seen)
            for key in seen:
                agg[key]["credit_note_count"] += 1

    rows: list[dict[str, Any]] = []
    for row in agg.values():
        row["gross_quantity"] = round(row["gross_quantity"], 3)
        row["gross_sales"] = round(row["gross_sales"], 2)
        row["return_quantity"] = round(row["return_quantity"], 3)
        row["return_value"] = round(row["return_value"], 2)
        row["net_quantity"] = round(row["gross_quantity"] - row["return_quantity"], 3)
        row["net_sales"] = round(row["gross_sales"] - row["return_value"], 2)
        rows.append(row)

    rows.sort(key=lambda x: float(x.get(sort_by) or 0), reverse=True)
    top_n = max(1, min(int(top_n), 200))

    return {
        "date_start": date_start,
        "date_end": date_end,
        "sort_by": sort_by,
        "include_credit_notes": include_credit_notes,
        "invoice_count": len(invoices),
        "credit_note_count": len(credit_notes),
        "invoice_detail_errors": invoice_detail_errors,
        "credit_note_detail_errors": credit_note_detail_errors,
        "items_count": len(rows),
        "items": rows[:top_n],
    }


@mcp.tool()
async def zoho_books_read(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Advanced read-only Zoho Books GET tool for endpoints not yet wrapped above.
    Pass a relative Books v3 path such as 'reports/...' or 'items'.
    This tool never sends POST/PUT/PATCH/DELETE requests.
    """
    if not path or path.startswith("/"):
        path = path.lstrip("/")
    blocked = ("settings/preferences",)
    if any(path.startswith(x) for x in blocked):
        raise ValueError("This endpoint is blocked in the read-only connector")
    return await _zoho_get(path, params)


security = TransportSecuritySettings(
    allowed_hosts=[ALLOWED_HOST, f"{ALLOWED_HOST}:*", "localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"],
    allowed_origins=[f"https://{ALLOWED_HOST}", f"http://{ALLOWED_HOST}", "http://localhost", "http://127.0.0.1"],
)

app = mcp.streamable_http_app(
    transport_security=security,
    json_response=True,
)
