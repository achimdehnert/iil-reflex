"""Prompts gehoeren nicht als Literal in den Python-Code (platform#1771 Welle 2).

iil-reflex ist eine Bibliothek (kein Django, kein promptfw-Konsument bislang).
Anders als in writing-hub (#503, ADR-083/146) verlangt dieser Guard hier NICHT
die Migration auf ein Vorlagen-Idiom — das waere ein Framework-Ausbau nebenbei
(platform#1771 §7, explizit nicht Teil dieser Welle). Er macht nur sichtbar,
WO LLM-Prompts inline im Code komponiert werden, mit einer begruendeten
Schuldenliste statt stillschweigender Duldung.

## Warum per AST und nicht per grep

Vorlage: `writing-hub/tests/test_prompts_go_through_promptfw.py`. Der dortige
Befund (#503) zeigte: ein grep nach `^_?[A-Z_]*PROMPT[A-Z_]* *=` sieht nur
Modul-Konstanten. Prompts, die als lokale Variable im Funktionsrumpf gebaut
werden (`prompt = (...)`), sieht das Muster nicht. Deshalb AST, nicht grep.

## Was als Prompt gilt

Ein Dict-Literal mit `role` **und** `content`, dessen `content` laenger als
`_MIN_PROMPTLAENGE` Zeichen ist. Oder eine Zuweisung an einen Namen, der nach
Prompt klingt (`prompt`, `PROMPT`, `ANWEISUNG`, `INSTRUCTION`, `SYSTEM_MSG`),
deren Wert laenger als `_MIN_PROMPTLAENGE` ist. Die Laengengrenze trennt echte
Prompts von Verdrahtungsproben (`{"role": "user", "content": "ok"}`).
"""

import ast
import re
from pathlib import Path

#: Kuerzere `content`-Werte sind Proben, keine Prompts. Bibliothek statt
#: Anwendung -> kleinere Datei-Sanity-Schwelle als im writing-hub-Original.
_MIN_PROMPTLAENGE = 40

#: Namen, die eine Zeichenkette als Prompt ausweisen.
_PROMPT_NAME = re.compile(r"PROMPT|ANWEISUNG|INSTRUCTION|SYSTEM_?MSG", re.IGNORECASE)

#: Paketwurzel: reflex/ neben diesem tests/-Verzeichnis. Kein Django ->
#: Path(__file__)-basiert statt settings.BASE_DIR.
_PAKET_WURZEL = Path(__file__).resolve().parent.parent / "reflex"


def _lang_genug(knoten) -> bool:
    """Traegt dieser Ausdruck genug Text, um ein Prompt zu sein?

    Deckt drei Schreibweisen ab: ein einfaches Literal, die implizite
    Verkettung mehrerer Literale in Klammern und f-Strings.
    """
    if isinstance(knoten, ast.Constant):
        return isinstance(knoten.value, str) and len(knoten.value) >= _MIN_PROMPTLAENGE
    if isinstance(knoten, ast.JoinedStr):
        return sum(len(t.value) for t in knoten.values if isinstance(t, ast.Constant)) >= _MIN_PROMPTLAENGE
    if isinstance(knoten, ast.BinOp):  # "a" + "b"
        return _lang_genug(knoten.left) or _lang_genug(knoten.right)
    return False


#: Bekannte Ausnahmen — jede mit Grund, keine stillschweigende.
#:
#: Das ist eine SCHULDENLISTE, keine Erlaubnis: wer hier etwas eintraegt, sagt
#: „noch nicht migriert", nicht „muss nicht". Sie soll schrumpfen.
AUSNAHMEN: dict[str, str] = {
    "classify.py": (
        "LLM-Prompt inline komponiert; iil-reflex hat kein Template-Lade-Idiom, "
        "dessen Einfuehrung ist eine Design-Entscheidung (kein Framework-Ausbau "
        "nebenbei, platform#1771 §7) — Abbau via Folge-Issue."
    ),
    "uc_dialog.py": (
        "LLM-Prompt inline komponiert; iil-reflex hat kein Template-Lade-Idiom, "
        "dessen Einfuehrung ist eine Design-Entscheidung (kein Framework-Ausbau "
        "nebenbei, platform#1771 §7) — Abbau via Folge-Issue."
    ),
}


def _python_dateien():
    return [
        p
        for p in _PAKET_WURZEL.rglob("*.py")
        if not any(teil.startswith(".") for teil in p.relative_to(_PAKET_WURZEL).parts) and "__pycache__" not in p.parts
    ]


def _prompt_stellen(pfad: Path) -> list[int]:
    try:
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover
        return []

    gefunden = []
    for knoten in ast.walk(baum):
        # (a) Zuweisung an einen Namen, der nach Prompt klingt.
        if isinstance(knoten, (ast.Assign, ast.AnnAssign)):
            ziele = knoten.targets if isinstance(knoten, ast.Assign) else [knoten.target]
            namen = [t.id for t in ziele if isinstance(t, ast.Name)]
            if any(_PROMPT_NAME.search(n) for n in namen) and _lang_genug(knoten.value):
                gefunden.append(knoten.lineno)
            continue

        # (b) messages-Dict mit role + content.
        if not isinstance(knoten, ast.Dict):
            continue
        schluessel = [k.value for k in knoten.keys if isinstance(k, ast.Constant)]
        if "role" not in schluessel or "content" not in schluessel:
            continue
        for k, v in zip(knoten.keys, knoten.values, strict=True):
            if not (isinstance(k, ast.Constant) and k.value == "content"):
                continue
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                if len(v.value) >= _MIN_PROMPTLAENGE:
                    gefunden.append(knoten.lineno)
            elif isinstance(v, ast.JoinedStr):  # f-string
                laenge = sum(len(t.value) for t in v.values if isinstance(t, ast.Constant))
                if laenge >= _MIN_PROMPTLAENGE:
                    gefunden.append(knoten.lineno)
    return gefunden


def test_should_actually_parse_the_package_tree():
    """Sonst ginge der Guard gruen durch, weil er nichts liest."""
    assert len(_python_dateien()) > 5


def test_should_find_prompts_when_they_exist():
    """Gegenprobe am eigenen Werkzeug: findet der Scanner ueberhaupt etwas?

    Ohne diesen Test belegt ein leeres Ergebnis unten gar nichts — es koennte
    genauso gut heissen, dass der Scanner kaputt ist.
    """
    import tempfile

    quelle = 'msgs = [{"role": "system", "content": "Du bist ein Lektor und bewertest Kapitel nach Stil."}]\n'
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(quelle)
        pfad = Path(f.name)
    try:
        assert _prompt_stellen(pfad), "Der Scanner findet einen offensichtlichen Prompt nicht"
    finally:
        pfad.unlink()


def test_should_find_the_very_violation_this_guard_was_written_for():
    """Realfall woertlich: `_ANFRAGE_PROMPT` als Zeichenketten-Konstante mit
    impliziter Verkettung, kein role/content-Dict. Ein Guard, der nur nach der
    einen Form sucht, die man gerade im Kopf hat, ist derselbe Fehler wie das
    grep-Muster, das den writing-hub-Befund #503 ausgeloest hat — nur eine
    Ebene weiter. Deshalb steht der Realfall hier woertlich.
    """
    import tempfile

    alte_form = (
        "_ANFRAGE_PROMPT = (\n"
        '    "Formuliere aus der folgenden Kapitelbeschreibung eine Suchanfrage fuer eine "\n'
        "    \"wissenschaftliche Literaturdatenbank, in der Sprache mit dem ISO-Code '{sprache}'.\"\n"
        ")\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(alte_form)
        pfad = Path(f.name)
    try:
        assert _prompt_stellen(pfad), "Der Guard findet den Fall nicht, fuer den er geschrieben wurde"
    finally:
        pfad.unlink()


def test_should_not_flag_a_short_constant_that_merely_mentions_prompt():
    """Gegenprobe: `STYLE_PROMPT_MAX_CHARS = 2000` ist kein Prompt."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("STYLE_PROMPT_MAX_CHARS = 2000\nMAX_CHARACTERS_IN_PROMPT = 5\n")
        pfad = Path(f.name)
    try:
        assert not _prompt_stellen(pfad)
    finally:
        pfad.unlink()


def test_should_not_find_a_prompt_in_a_wiring_probe():
    """Gegenprobe andersherum — `content='ok'` ist kein Prompt."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write('msgs = [{"role": "user", "content": "ok"}]\n')
        pfad = Path(f.name)
    try:
        assert not _prompt_stellen(pfad)
    finally:
        pfad.unlink()


def test_should_route_every_prompt_through_promptfw():
    verstoesse = []
    for pfad in _python_dateien():
        relativ = str(pfad.relative_to(_PAKET_WURZEL))
        if relativ in AUSNAHMEN:
            continue
        for zeile in _prompt_stellen(pfad):
            verstoesse.append(f"{relativ}:{zeile}")

    assert not verstoesse, (
        "Prompt-Text als Literal im Python-Code:\n  "
        + "\n  ".join(sorted(verstoesse))
        + "\n\nEin Literal hier ist nicht zentral aenderbar/versionierbar und "
        "faellt unter keinen Prompt-Guard. iil-reflex hat aktuell kein "
        "Vorlagen-Idiom (bewusst, platform#1771 §7 — kein Framework-Ausbau "
        "nebenbei). Entweder gehoert die Datei mit Grund in AUSNAHMEN — "
        "sichtbar, nicht stillschweigend — oder das Vorlagen-Idiom wird per "
        "eigenem ADR/Issue entschieden."
    )


def test_should_keep_the_exception_list_honest():
    """Eine Ausnahme fuer eine Datei ohne Prompt ist ein Alteintrag, der taeuscht."""
    tot = [name for name in AUSNAHMEN if not (_PAKET_WURZEL / name).exists()]
    assert not tot, f"AUSNAHMEN nennt Dateien, die es nicht mehr gibt: {tot}"
