import json
import logging
import secrets
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from . import importer
from .backup import backup_database
from .forms import ArticleForm, ImportUploadForm, PersonForm
from .models import Article, Category, Person

log = logging.getLogger(__name__)


def start(request):
    categories = Category.objects.annotate(
        in_stock=Count("articles", filter=Q(articles__status=Article.Status.STOCK))
    )
    stock = Article.objects.filter(status=Article.Status.STOCK)
    open_payouts = Article.objects.filter(status=Article.Status.SOLD)
    return render(
        request,
        "inventar/start.html",
        {
            "categories": categories,
            "stock_count": stock.count(),
            "stock_value": stock.aggregate(s=Sum("price"))["s"] or Decimal("0"),
            "open_payout_count": open_payouts.count(),
            "open_payout_sum": open_payouts.aggregate(s=Sum("owner_amount"))["s"] or Decimal("0"),
            "person_count": Person.objects.count(),
        },
    )


# --- Artikel --------------------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def article_create(request):
    categories = Category.objects.all()
    category = categories.filter(code=request.GET.get("kategorie")).first()
    owner = Person.objects.filter(pk=request.GET.get("besitzerin") or None).first()
    if request.method == "POST":
        form = ArticleForm(request.POST)
        if form.is_valid():
            article = form.save()
            messages.success(request, f"Artikel {article.label} gespeichert: {article.description}")
            # Serienerfassung: gleiche Kategorie und Besitzerin bleiben gesetzt
            return redirect(
                f"{request.path}?kategorie={article.category.code}&besitzerin={article.owner_id}"
            )
    else:
        initial = {"owner": owner}
        if category:
            initial |= {"category": category, "number": category.next_number()}
        form = ArticleForm(initial=initial)
    return render(
        request,
        "inventar/article_form.html",
        {"form": form, "categories": categories, "category": category, "owner": owner, "sizes": _known_sizes()},
    )


@require_http_methods(["GET", "POST"])
def article_edit(request, pk):
    article = get_object_or_404(Article, pk=pk)
    form = ArticleForm(request.POST or None, instance=article)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Artikel {article.label} gespeichert.")
        return redirect("article_list")
    return render(
        request,
        "inventar/article_form.html",
        {"form": form, "article": article, "categories": Category.objects.all(), "sizes": _known_sizes()},
    )


def article_list(request):
    articles = Article.objects.select_related("category", "owner")
    q = request.GET.get("q", "").strip()
    category = request.GET.get("kategorie", "")
    status = request.GET.get("status", Article.Status.STOCK)
    if q:
        match = Q(description__icontains=q) | Q(size__icontains=q) | Q(owner__name__icontains=q)
        if q.isdigit():
            match |= Q(number=int(q))
        articles = articles.filter(match)
    if category:
        articles = articles.filter(category__code=category)
    if status:
        articles = articles.filter(status=status)
    return render(
        request,
        "inventar/article_list.html",
        {
            "articles": articles,
            "count": articles.count(),
            "total": articles.aggregate(s=Sum("price"))["s"] or Decimal("0"),
            "categories": Category.objects.all(),
            "statuses": Article.Status.choices,
            "q": q,
            "category": category,
            "status": status,
        },
    )


def _known_sizes() -> list[str]:
    return list(Article.objects.exclude(size="").values_list("size", flat=True).distinct().order_by("size"))


# --- Kunden ---------------------------------------------------------------------------------------


def person_list(request):
    q = request.GET.get("q", "").strip()
    persons = Person.objects.annotate(
        in_stock=Count("articles", filter=Q(articles__status=Article.Status.STOCK)),
        sold=Count("articles", filter=Q(articles__status__in=[Article.Status.SOLD, Article.Status.PAID])),
        open_payout=Sum("articles__owner_amount", filter=Q(articles__status=Article.Status.SOLD)),
    )
    if q:
        persons = persons.filter(
            Q(name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q) | Q(notes__icontains=q)
        )
    return render(request, "inventar/person_list.html", {"persons": persons, "q": q})


def person_detail(request, pk):
    person = get_object_or_404(Person, pk=pk)
    articles = person.articles.select_related("category")
    return render(
        request,
        "inventar/person_detail.html",
        {
            "person": person,
            "articles": articles,
            "purchases": person.purchases.select_related("category"),
            "open_payout": articles.filter(status=Article.Status.SOLD).aggregate(s=Sum("owner_amount"))["s"],
            "paid_total": articles.filter(status=Article.Status.PAID).aggregate(s=Sum("owner_amount"))["s"],
        },
    )


@require_http_methods(["GET", "POST"])
def person_edit(request, pk=None):
    person = get_object_or_404(Person, pk=pk) if pk else None
    form = PersonForm(request.POST or None, instance=person)
    if request.method == "POST" and form.is_valid():
        person = form.save()
        messages.success(request, f"{person.name} gespeichert.")
        return redirect("person_detail", pk=person.pk)
    return render(request, "inventar/person_form.html", {"form": form, "person": person})


# --- Import ---------------------------------------------------------------------------------------


def _import_dir() -> Path:
    path = settings.DATA_DIR / "import"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _result_file(token: str) -> Path:
    if not token.isalnum():
        raise Http404
    return _import_dir() / f"{token}.json"


@require_http_methods(["GET", "POST"])
def import_upload(request):
    form = ImportUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        token = secrets.token_hex(8)
        tmp = _import_dir() / f"upload-{token}{Path(upload.name).suffix.lower()}"
        try:
            with tmp.open("wb") as out:
                for chunk in upload.chunks():
                    out.write(chunk)
            rows = importer.read_rows(tmp)
            result = importer.analyze(rows, {c.code: c.start_number for c in Category.objects.all()})
        except importer.ImportFehler as error:
            form.add_error("file", str(error))
        except Exception:
            log.exception("Import fehlgeschlagen")
            form.add_error("file", "Die Datei konnte nicht gelesen werden.")
        else:
            result["file_name"] = upload.name
            _result_file(token).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            return redirect("import_preview", token=token)
        finally:
            tmp.unlink(missing_ok=True)
    return render(
        request, "inventar/import_upload.html", {"form": form, "existing": Article.objects.count()}
    )


@require_http_methods(["GET", "POST"])
def import_preview(request, token):
    file = _result_file(token)
    if not file.exists():
        raise Http404
    result = json.loads(file.read_text(encoding="utf-8"))
    if request.method == "POST":
        decisions = {i["id"]: request.POST.get(i["id"], "") for i in result["issues"]}
        backup = backup_database("vor-import")
        stats = importer.apply(result, decisions)
        file.unlink(missing_ok=True)
        messages.success(
            request,
            f"Import fertig: {stats['articles']} Artikel und {stats['persons']} Personen übernommen. "
            f"Sicherung vorher: {backup.name}",
        )
        for label, description in stats["suffixed"]:
            messages.info(request, f"Nummer {label} (doppelt beschriftet): {description}")
        for old, new, description in stats["renumbered"]:
            messages.info(request, f"Neue Nummer {new} (vorher {old or 'keine'}): {description}")
        if stats["skipped"]:
            messages.warning(request, f"{stats['skipped']} Artikel ohne bekannte Kategorie übersprungen.")
        return redirect("article_list")
    return render(
        request,
        "inventar/import_preview.html",
        {
            "result": result,
            "summary": result["summary"],
            "issues": _issue_views(result),
            "existing": Article.objects.count(),
        },
    )


ISSUE_TITLES = {
    "duplicate": "Doppelte Nummer",
    "price": "Preis ohne Zahl",
    "sold_before_intake": "Verkauft vor dem Eingang",
    "contact": "Verschiedene Kontakte",
    "no_number": "Artikel ohne Nummer",
    "unknown_category": "Unbekannte Kategorie",
    "range": "Nummer passt nicht zur Kategorie",
    "no_owner": "Ohne Besitzerin",
}
ISSUE_ORDER = list(ISSUE_TITLES)


def _issue_views(result) -> list[dict]:
    """Unstimmigkeiten für die Vorschau, mit den betroffenen Zeilen der Liste."""
    articles, people = result["articles"], result["people"]
    views = []
    for issue in sorted(result["issues"], key=lambda i: ISSUE_ORDER.index(i["type"])):
        view = dict(issue, title=ISSUE_TITLES[issue["type"]])
        if "rows" in issue:
            # Nummer, wie sie beim Behalten aller Artikel heisst: 1096, 1096+, …
            view["articles"] = [
                dict(articles[r], index=r, preview_label=f"{issue['number']}{'+' * n}")
                for n, r in enumerate(issue["rows"])
            ]
        if "row" in issue:
            view["article"] = articles[issue["row"]]
        if "person" in issue:
            view["person_data"] = people[issue["person"]]
        views.append(view)
    return views
