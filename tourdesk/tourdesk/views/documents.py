from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import flash_errors
from ..forms import CONTRACT_FIELDS, INVOICE_FIELDS, populate
from ..models import CONTRACT_STATUSES, INVOICE_KINDS, INVOICE_STATUSES, Agency, Contract, Invoice, InvoiceLine, Show, db
from ..services import create_contract, create_invoice_for_show, issue_invoice, totals_by_currency

bp = Blueprint("documents", __name__)


# --------------------------------------------------------------------------
# Contracts
# --------------------------------------------------------------------------


@bp.route("/contracts")
def contracts():
    status = request.args.get("status", "")
    query = Contract.query.join(Show).order_by(Show.date.desc())
    if status:
        query = query.filter(Contract.status == status)
    return render_template("contracts/list.html", contracts=query.all(), statuses=CONTRACT_STATUSES, status=status)


@bp.route("/shows/<int:show_id>/contracts", methods=["POST"])
def contract_create(show_id):
    show = db.get_or_404(Show, show_id)
    contract = create_contract(show)
    db.session.commit()
    flash(f"Contract {contract.number} drafted from the template. Review it before sending.", "success")
    return redirect(url_for(".contract_edit", contract_id=contract.id))


@bp.route("/contracts/<int:contract_id>")
def contract(contract_id):
    contract = db.get_or_404(Contract, contract_id)
    return render_template("contracts/view.html", contract=contract, print_mode=request.args.get("print") == "1")


@bp.route("/contracts/<int:contract_id>/edit", methods=["GET", "POST"])
def contract_edit(contract_id):
    contract = db.get_or_404(Contract, contract_id)
    if request.method == "POST":
        errors = populate(contract, CONTRACT_FIELDS, request.form)
        if errors:
            flash_errors(errors)
            db.session.rollback()
        else:
            if contract.status == "sent" and not contract.sent_at:
                contract.sent_at = date.today()
            if contract.status == "signed" and not contract.signed_at:
                contract.signed_at = date.today()
            db.session.commit()
            flash("Contract saved.", "success")
            return redirect(url_for(".contract", contract_id=contract.id))
    return render_template(
        "form_page.html",
        title=f"Contract {contract.number} · {contract.show.title}",
        fields=CONTRACT_FIELDS,
        obj=contract,
        cancel_url=url_for(".contract", contract_id=contract.id),
    )


@bp.route("/contracts/<int:contract_id>/status", methods=["POST"])
def contract_status(contract_id):
    contract = db.get_or_404(Contract, contract_id)
    status = request.form.get("status")
    if status not in dict(CONTRACT_STATUSES):
        abort(400)
    contract.status = status
    if status == "sent" and not contract.sent_at:
        contract.sent_at = date.today()
    if status == "signed":
        contract.signed_at = contract.signed_at or date.today()
        # A signed contract is the usual trigger to confirm the show.
        if contract.show.status in ("option", "pending"):
            contract.show.status = "confirmed"
    db.session.commit()
    flash(f"Contract marked as {status}.", "success")
    return redirect(url_for(".contract", contract_id=contract.id))


@bp.route("/contracts/<int:contract_id>/delete", methods=["POST"])
def contract_delete(contract_id):
    contract = db.get_or_404(Contract, contract_id)
    show_id = contract.show_id
    if contract.status == "signed":
        flash("Signed contracts can't be deleted. Mark it cancelled instead.", "error")
        return redirect(url_for(".contract", contract_id=contract.id))
    db.session.delete(contract)
    db.session.commit()
    flash("Contract deleted.", "success")
    return redirect(url_for("shows.show", show_id=show_id))


# --------------------------------------------------------------------------
# Invoices
# --------------------------------------------------------------------------


@bp.route("/invoices")
def invoices():
    status = request.args.get("status", "")
    query = Invoice.query.order_by(Invoice.created_at.desc())
    if status == "overdue":
        query = query.filter(Invoice.status == "sent", Invoice.due_date < date.today())
    elif status:
        query = query.filter(Invoice.status == status)
    invoices = query.all()
    outstanding = Invoice.query.filter_by(status="sent").all()
    return render_template(
        "invoices/list.html",
        invoices=invoices,
        statuses=INVOICE_STATUSES,
        status=status,
        outstanding_totals=totals_by_currency(outstanding),
    )


@bp.route("/shows/<int:show_id>/invoices", methods=["POST"])
def invoice_create(show_id):
    show = db.get_or_404(Show, show_id)
    kind = request.form.get("kind", "full")
    if kind not in dict(INVOICE_KINDS):
        abort(400)
    invoice = create_invoice_for_show(show, kind)
    db.session.commit()
    flash("Draft invoice created. Check the lines, then issue it to give it a number.", "success")
    return redirect(url_for(".invoice", invoice_id=invoice.id))


@bp.route("/invoices/new", methods=["GET", "POST"])
def invoice_new():
    """A blank invoice not tied to a show (merch, production costs, etc)."""
    agency = Agency.get()
    invoice = Invoice(kind="other", currency=agency.default_currency, vat_rate=agency.default_vat_rate or 0)
    if request.method == "POST":
        errors = populate(invoice, INVOICE_FIELDS, request.form)
        if errors:
            flash_errors(errors)
        else:
            db.session.add(invoice)
            db.session.commit()
            return redirect(url_for(".invoice", invoice_id=invoice.id))
    return render_template("form_page.html", title="New invoice", fields=INVOICE_FIELDS, obj=invoice, cancel_url=url_for(".invoices"))


@bp.route("/invoices/<int:invoice_id>")
def invoice(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    return render_template(
        "invoices/view.html", invoice=invoice, print_mode=request.args.get("print") == "1", statuses=INVOICE_STATUSES
    )


@bp.route("/invoices/<int:invoice_id>/edit", methods=["GET", "POST"])
def invoice_edit(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    if invoice.status != "draft":
        flash("Issued invoices are locked. Cancel it and create a new one to make changes.", "error")
        return redirect(url_for(".invoice", invoice_id=invoice.id))
    if request.method == "POST":
        errors = populate(invoice, INVOICE_FIELDS, request.form)
        if errors:
            flash_errors(errors)
            db.session.rollback()
        else:
            db.session.commit()
            flash("Invoice saved.", "success")
            return redirect(url_for(".invoice", invoice_id=invoice.id))
    return render_template(
        "form_page.html",
        title=f"Edit {invoice.display_number}",
        fields=INVOICE_FIELDS,
        obj=invoice,
        cancel_url=url_for(".invoice", invoice_id=invoice.id),
    )


def _draft_or_redirect(invoice):
    if invoice.status != "draft":
        flash("Issued invoices are locked.", "error")
        return redirect(url_for(".invoice", invoice_id=invoice.id))
    return None


@bp.route("/invoices/<int:invoice_id>/lines", methods=["POST"])
def invoice_line_add(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    if response := _draft_or_redirect(invoice):
        return response
    description = request.form.get("description", "").strip()
    try:
        quantity = float(request.form.get("quantity") or 1)
        unit_price = Decimal((request.form.get("unit_price") or "0").replace(",", ""))
    except (ValueError, InvalidOperation):
        flash("Quantity and price must be numbers.", "error")
        return redirect(url_for(".invoice", invoice_id=invoice.id))
    if not description:
        flash("A line needs a description.", "error")
    else:
        invoice.lines.append(InvoiceLine(description=description, quantity=quantity, unit_price=unit_price))
        db.session.commit()
    return redirect(url_for(".invoice", invoice_id=invoice.id))


@bp.route("/invoice-lines/<int:line_id>/delete", methods=["POST"])
def invoice_line_delete(line_id):
    line = db.get_or_404(InvoiceLine, line_id)
    invoice = line.invoice
    if response := _draft_or_redirect(invoice):
        return response
    db.session.delete(line)
    db.session.commit()
    return redirect(url_for(".invoice", invoice_id=invoice.id))


@bp.route("/invoices/<int:invoice_id>/issue", methods=["POST"])
def invoice_issue(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    if not invoice.lines:
        flash("Add at least one line before issuing.", "error")
    elif not invoice.bill_to_name:
        flash("Fill in who the invoice is billed to before issuing.", "error")
    else:
        issue_invoice(invoice)
        db.session.commit()
        flash(f"Invoice {invoice.number} issued.", "success")
    return redirect(url_for(".invoice", invoice_id=invoice.id))


@bp.route("/invoices/<int:invoice_id>/paid", methods=["POST"])
def invoice_paid(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    if invoice.status != "sent":
        abort(400)
    invoice.status = "paid"
    invoice.paid_at = date.today()
    db.session.commit()
    flash(f"{invoice.number} marked as paid.", "success")
    return redirect(url_for(".invoice", invoice_id=invoice.id))


@bp.route("/invoices/<int:invoice_id>/cancel", methods=["POST"])
def invoice_cancel(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    if invoice.status == "draft":
        show_id = invoice.show_id
        db.session.delete(invoice)
        db.session.commit()
        flash("Draft deleted.", "success")
        return redirect(url_for("shows.show", show_id=show_id) if show_id else url_for(".invoices"))
    invoice.status = "cancelled"
    db.session.commit()
    flash(f"{invoice.number} cancelled. Its number stays reserved.", "success")
    return redirect(url_for(".invoice", invoice_id=invoice.id))
