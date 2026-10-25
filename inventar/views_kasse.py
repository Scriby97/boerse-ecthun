"""Kasse, Verkäufe, Verkauft-Übersicht, Abrechnen und Clubartikel."""

import re
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from . import reports, sales
from .forms import CheckoutForm, ClubItemForm, ClubSaleForm, OtherItemForm, PayoutForm
from .models import AppSettings, Article, ClubItem, Payout, Person, Sale, SaleItem
from .delivery import PDF, deliver
from .pdf import receipt_pdf
from .persons import sort_key

CART = "kasse"
CENT = Decimal("0.01")
_LABEL = re.compile(r"\s*(\d+)\s*(\+*)\s*")


# --- Warenkorb (in der Sitzung) -------------------------------------------------------------------


def _cart(request) -> list[dict]:
    return request.session.get(CART, [])


def _save_cart(request, entries: list[dict]) -> None:
    request.session[CART] = entries


def _add(request, entry: dict) -> None:
    _save_cart(request, _cart(request) + [entry])


def _article_entry(article: Article) -> dict:
    return {
        "kind": SaleItem.Kind.ARTICLE,
        "article_id": article.pk,
        "label": article.label,
        "description": article.description,
        "size": article.size,
        "owner": article.owner.name,
        "price": str(article.price if article.price is not None else Decimal("0.00")),
        "note": article.price_note,
        # nur zur Information an der Kasse, kommt nicht auf die Quittung
        "extra": article.extra_info,
    }


def kasse(request):
    entries = _cart(request)
    total = sum((Decimal(e["price"]) for e in entries), Decimal("0"))
    return render(request, "inventar/kasse.html", {
        "entries": entries,
        "total": total,
        "choices": request.session.pop("kasse_choices", None),
        "other_form": OtherItemForm(),
        "club_form": ClubSaleForm(),
        "checkout_form": CheckoutForm(initial={"date": timezone.localdate()}),
    })


@require_POST
def kasse_add_number(request):
    """Nummer eingeben, Enter: Artikel kommt in den Warenkorb. Bei 1096 und 1096+ fragt die Kasse nach."""
    m = _LABEL.fullmatch(request.POST.get("nummer", ""))
    if not m:
        messages.error(request, "Bitte eine Artikelnummer eingeben, z. B. 10234 oder 1096+.")
        return redirect("kasse")
    number, suffix = int(m.group(1)), m.group(2)
    in_cart = {e.get("article_id") for e in _cart(request)}
    stock = Article.objects.filter(number=number, status=Article.Status.STOCK).select_related("owner")
    if suffix:
        stock = stock.filter(number_suffix=suffix)
    candidates = [a for a in stock if a.pk not in in_cart]
    if len(candidates) == 1:
        _add(request, _article_entry(candidates[0]))
    elif len(candidates) > 1:
        request.session["kasse_choices"] = [_article_entry(a) for a in candidates]
    elif stock.exists():
        messages.warning(request, f"Artikel {number}{suffix} ist schon im Warenkorb.")
    else:
        other = Article.objects.filter(number=number, number_suffix=suffix).first()
        if other:
            when = f" am {other.sold_date:%d.%m.%Y}" if other.sold_date else ""
            messages.error(request, f"Artikel {other.label} ist nicht an Lager ({other.get_status_display()}{when}).")
        else:
            messages.error(request, f"Die Nummer {number}{suffix} gibt es nicht.")
    return redirect("kasse")


@require_POST
def kasse_add_article(request, pk):
    article = get_object_or_404(Article, pk=pk, status=Article.Status.STOCK)
    if article.pk not in {e.get("article_id") for e in _cart(request)}:
        _add(request, _article_entry(article))
    return redirect("kasse")


@require_POST
def kasse_add_other(request):
    form = OtherItemForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte Bezeichnung und Preis angeben.")
        return redirect("kasse")
    owner = form.cleaned_data["owner"]
    _add(request, {
        "kind": SaleItem.Kind.OTHER if owner else SaleItem.Kind.OWN,
        "owner_id": owner.pk if owner else None,
        "owner": owner.name if owner else "eigener Artikel",
        "label": "",
        "description": form.cleaned_data["description"],
        "size": form.cleaned_data["size"],
        "price": str(form.cleaned_data["price"].quantize(CENT)),
    })
    return redirect("kasse")


@require_POST
def kasse_add_club(request):
    form = ClubSaleForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte einen Clubartikel wählen.")
        return redirect("kasse")
    item: ClubItem = form.cleaned_data["club_item"]
    price = form.cleaned_data["price"]
    if item.stock <= 0:
        messages.warning(request, f"{item}: laut Bestand keiner mehr da. Bitte den Bestand prüfen.")
    _add(request, {
        "kind": SaleItem.Kind.CLUB,
        "club_item_id": item.pk,
        "owner": "Club EC Thun",
        "label": "Club",
        "description": item.name,
        "size": form.cleaned_data["size"] or item.size,
        "price": str((price if price is not None else item.customer_price).quantize(CENT)),
    })
    return redirect("kasse")


@require_POST
def kasse_price(request, index):
    entries = _cart(request)
    raw = request.POST.get("price", "").replace(",", ".").strip()
    try:
        price = Decimal(raw).quantize(Decimal("0.01"))
        if price < 0:
            raise ValueError
    except (ArithmeticError, ValueError):
        messages.error(request, "Ungültiger Preis.")
        return redirect("kasse")
    if 0 <= index < len(entries):
        entries[index]["price"] = str(price)
        _save_cart(request, entries)
    return redirect("kasse")


@require_POST
def kasse_remove(request, index):
    entries = _cart(request)
    if 0 <= index < len(entries):
        entries.pop(index)
        _save_cart(request, entries)
    return redirect("kasse")


@require_POST
def kasse_clear(request):
    _save_cart(request, [])
    return redirect("kasse")


@require_POST
def kasse_checkout(request):
    form = CheckoutForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte Datum und Zahlungsart prüfen.")
        return redirect("kasse")
    buyer = form.cleaned_data["buyer"]
    if not buyer and form.cleaned_data["new_buyer"].strip():
        buyer = Person.objects.create(name=form.cleaned_data["new_buyer"].strip())
    try:
        sale = sales.create_sale(_cart(request), buyer=buyer, payment=form.cleaned_data["payment"],
                                 date=form.cleaned_data["date"])
    except sales.SaleError as error:
        messages.error(request, str(error))
        return redirect("kasse")
    _save_cart(request, [])
    messages.success(request, f"Verkauft: Quittung Nr. {sale.number} über CHF {sale.total:.2f}.")
    return redirect("sale_detail", pk=sale.pk)


# --- Verkauf --------------------------------------------------------------------------------------


def sale_detail(request, pk):
    sale = get_object_or_404(Sale.objects.select_related("buyer"), pk=pk)
    items = list(sale.items.select_related("owner", "article", "payout"))
    # Direkt nach dem Verkauf auszahlen: offene Anteile dieses Verkaufs pro Besitzerin
    to_pay: dict[int, dict] = {}
    for item in items:
        if item.owner and item.owner_amount > 0 and not item.payout and not sale.cancelled_at:
            entry = to_pay.setdefault(item.owner_id, {"person": item.owner, "amount": Decimal("0")})
            entry["amount"] += item.owner_amount
    return render(request, "inventar/sale_detail.html", {
        "people": sorted(Person.objects.all(), key=lambda p: sort_key(p.name)),
        "sale": sale,
        "items": items,
        "to_pay": list(to_pay.values()),
        "methods": Payout.Method.choices,
    })


@require_POST
def sale_buyer(request, pk):
    """Käuferin nachträglich erfassen oder ändern (auch bei den Artikeln des Verkaufs)."""
    sale = get_object_or_404(Sale, pk=pk)
    buyer = Person.objects.filter(pk=request.POST.get("buyer") or 0).first()
    new_name = " ".join(request.POST.get("new_buyer", "").split())
    if not buyer and new_name:
        buyer = Person.objects.filter(name__iexact=new_name).first() or Person.objects.create(name=new_name)
    sale.buyer = buyer
    sale.save(update_fields=["buyer"])
    Article.objects.filter(sale_items__sale=sale).update(buyer=buyer)
    messages.success(request, f"Käuferin: {buyer.name}." if buyer else "Käuferin entfernt.")
    return redirect("sale_detail", pk=sale.pk)


@require_POST
def sale_descriptions(request, pk):
    """Bezeichnungen auf der Quittung anpassen (ändert nur die Quittung, nicht den Artikel im Inventar)."""
    sale = get_object_or_404(Sale, pk=pk)
    changed = 0
    for item in sale.items.all():
        text = " ".join(request.POST.get(f"bezeichnung-{item.pk}", "").split())
        if text and text != item.description:
            item.description = text[:300]
            item.save(update_fields=["description"])
            changed += 1
    messages.success(request, f"{changed} Bezeichnung(en) für die Quittung angepasst." if changed else "Keine Änderung.")
    if request.POST.get("pdf"):
        return redirect("sale_receipt", pk=sale.pk)
    return redirect("sale_detail", pk=sale.pk)


def sale_receipt(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    return deliver(request, receipt_pdf(sale, AppSettings.load()), f"Quittung-{sale.number}.pdf", PDF)


@require_POST
def sale_cancel(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    try:
        sales.cancel_sale(sale)
    except sales.SaleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Quittung Nr. {sale.number} storniert. Die Artikel sind wieder an Lager.")
    return redirect("sale_detail", pk=sale.pk)


@require_POST
def sale_payout(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    person = get_object_or_404(Person, pk=request.POST.get("person"))
    method = request.POST.get("method")
    if method not in Payout.Method.values:
        messages.error(request, "Bitte die Art der Auszahlung wählen.")
        return redirect("sale_detail", pk=sale.pk)
    try:
        payout = sales.record_payout(person, method, sale=sale)
    except sales.SaleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"{person.name}: CHF {payout.amount:.2f} per {payout.get_method_display()} ausbezahlt.")
    return redirect("sale_detail", pk=sale.pk)


def sale_list(request):
    period = request.GET.get("periode", "monat")
    if period not in reports.PERIODS:
        period = "monat"
    groups = reports.summarize(period)
    selected_key = request.GET.get("zeitraum") or (groups[0].key if groups else None)
    selected = next((g for g in groups if g.key == selected_key), None)
    return render(request, "inventar/sale_list.html", {
        "period": period,
        "periods": reports.PERIODS,
        "groups": groups,
        "total": reports.totals(groups),
        "selected": selected,
        "recent_sales": Sale.objects.select_related("buyer").prefetch_related("items")[:15],
    })


# --- Abrechnen ------------------------------------------------------------------------------------


def payout_list(request):
    amounts = sales.open_amounts()
    persons = {p.pk: p for p in Person.objects.filter(pk__in=amounts)}
    open_rows = sorted(({"person": persons[pk], "amount": amount} for pk, amount in amounts.items()),
                       key=lambda r: r["person"].name)
    return render(request, "inventar/payout_list.html", {
        "open_rows": open_rows,
        "open_total": sum(amounts.values(), Decimal("0")),
        "payouts": Payout.objects.select_related("person")[:50],
        "form": PayoutForm(),
    })


@require_POST
def payout_person(request, pk):
    person = get_object_or_404(Person, pk=pk)
    form = PayoutForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte die Art der Auszahlung wählen.")
        return redirect(request.POST.get("next") or "payout_list")
    try:
        payout = sales.record_payout(person, form.cleaned_data["method"], date=form.cleaned_data["date"])
    except sales.SaleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"{person.name}: CHF {payout.amount:.2f} per {payout.get_method_display()} ausbezahlt.")
    next_url = request.POST.get("next", "")
    return redirect(next_url if next_url.startswith("/") else "payout_list")


# --- Clubartikel ----------------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def club_item_edit(request, pk):
    item = get_object_or_404(ClubItem, pk=pk)
    form = ClubItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{item} gespeichert.")
        return redirect("club_items")
    return render(request, "inventar/club_item_form.html", {"item": item, "form": form})
