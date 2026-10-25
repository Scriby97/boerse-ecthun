from boerse import __version__


def app_version(request):
    return {"app_version": __version__}


def open_statements(request):
    """Anzahl offener Tagesabrechnungen für das Zeichen bei «Abrechnen» in der Navigation."""
    from .sales import daily_groups

    return {"open_statements": len(daily_groups())}
