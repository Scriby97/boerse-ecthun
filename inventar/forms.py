from django import forms

from .importer import SUFFIXES
from .models import Article, Person


class ArticleForm(forms.ModelForm):
    new_owner = forms.CharField(
        label="oder neue Besitzerin",
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Nachname Vorname"}),
    )

    class Meta:
        model = Article
        fields = [
            "category",
            "number",
            "number_suffix",
            "owner",
            "description",
            "size",
            "price",
            "price_note",
            "owner_share",
            "intake_date",
            "notes",
        ]
        widgets = {
            "intake_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "size": forms.TextInput(attrs={"list": "sizes", "autocomplete": "off"}),
            "description": forms.TextInput(attrs={"autofocus": True}),
        }

    field_order = ["category", "number", "number_suffix", "owner", "new_owner", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].required = False
        self.fields["owner"].empty_label = "– Besitzerin wählen –"

    def clean(self):
        data = super().clean()
        if not data.get("owner") and not data.get("new_owner"):
            self.add_error("owner", "Bitte eine Besitzerin wählen oder neu erfassen.")
        return data

    def save(self, commit=True):
        if not self.cleaned_data.get("owner"):
            self.instance.owner = Person.objects.create(name=self.cleaned_data["new_owner"].strip())
        return super().save(commit)


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ["name", "phone", "email", "twint", "address", "iban", "owner_share", "notes"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class ImportUploadForm(forms.Form):
    file = forms.FileField(label="Inventarliste (Numbers, Excel oder CSV)")

    def clean_file(self):
        file = self.cleaned_data["file"]
        if not file.name.lower().endswith(SUFFIXES):
            raise forms.ValidationError("Bitte eine Numbers-, Excel- oder CSV-Datei wählen.")
        return file
