"""Paint a Java file the way IntelliJ would with a given .icls scheme, compare it character by
character with what VS Code paints, and write an HTML report.

    python3 tools/compare.py \
        --scheme "Earl Grey.icls" \
        --intellij-spans build/intellij_spans.json \
        --vscode build/vscode_render.json \
        --source samples/Showcase.java \
        --intellij-src <intellij-community checkout> \
        --out docs/comparison.html

IntelliJ side, from the IntelliJ Community sources:
  * attribute lookup:  EditorColorsSchemeImpl.getAttributes / AbstractColorsScheme.getFallbackAttributes,
                       parent scheme "Default" from platform-resources/src/DefaultColorSchemesManager.xml,
                       fallback keys from JavaHighlightingColors + DefaultLanguageHighlighterColors;
  * lexer keys:        LayeredTextAttributes.create -> TextAttributes.merge (font types are OR-ed);
  * highlight infos:   IterationState: topmost non-null foreground, topmost non-plain font type.
"""
import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

# ------------------------------------------------------------------ IntelliJ key fallbacks


def read_fallbacks(intellij_src):
    """external key name -> fallback external key name, parsed from the IntelliJ sources."""
    files = [
        "platform/core-api/src/com/intellij/openapi/editor/DefaultLanguageHighlighterColors.java",
        "java/java-frontback-psi-impl/src/com/intellij/ide/highlighter/JavaHighlightingColors.java",
    ]
    var_to_name = {"HighlighterColors.TEXT": "TEXT"}
    fallback_var = {}
    for f in files:
        text = (Path(intellij_src) / f).read_text()
        cls = Path(f).stem
        for m in re.finditer(r'TextAttributesKey (\w+) = TextAttributesKey\.createTextAttributesKey\("(\w+)"(?:,\s*([\w.]+|\(TextAttributesKey\)null))?\)', text):
            var, name, fb = m.groups()
            var_to_name[var] = name
            var_to_name[cls + "." + var] = name
            if fb and "null" not in fb:
                fallback_var[name] = fb
    fallbacks = {}
    for name, fb in fallback_var.items():
        fallbacks[name] = var_to_name.get(fb) or var_to_name.get(fb.split(".")[-1])
    return fallbacks


# ------------------------------------------------------------------ schemes

INHERITED = object()


def parse_attrs(attributes_el):
    out = {}
    for opt in attributes_el.findall("option"):
        name = opt.get("name")
        if opt.get("baseAttributes") is not None:
            out[name] = INHERITED
            continue
        value = opt.find("value")
        if value is None:
            continue
        a = {"fg": None, "bg": None, "font": 0, "effect_color": None, "effect": None}
        for o in value.findall("option"):
            n, v = o.get("name"), o.get("value")
            if n == "FOREGROUND" and v:
                a["fg"] = "#" + v.upper().rjust(6, "0")
            elif n == "BACKGROUND" and v:
                a["bg"] = "#" + v.upper().rjust(6, "0")
            elif n == "FONT_TYPE" and v and v.isdigit():
                a["font"] = int(v)
            elif n == "EFFECT_COLOR" and v:
                a["effect_color"] = "#" + v.upper().rjust(6, "0")
            elif n == "EFFECT_TYPE" and v and v.lstrip("-").isdigit():
                a["effect"] = int(v)
        out[name] = a
    return out


class Scheme:
    def __init__(self, attrs, parent, fallbacks):
        self.attrs, self.parent, self.fallbacks = attrs, parent, fallbacks

    def direct(self, key):
        return self.attrs.get(key)

    def get(self, key):
        """EditorColorsSchemeImpl.getAttributes"""
        a = self.direct(key)
        if a is not None and a is not INHERITED:
            return a
        fb = self.fallbacks.get(key)
        if fb:
            cur = fb
            while True:                                   # AbstractColorsScheme.getFallbackAttributes
                attrs = self.direct(cur)
                nxt = self.fallbacks.get(cur)
                if attrs is not None and (attrs is not INHERITED or nxt is None):
                    return None if attrs is INHERITED else attrs
                if nxt is None:
                    break
                cur = nxt
        return self.parent.get(key) if self.parent else None


def load_schemes(icls_path, intellij_src):
    fallbacks = read_fallbacks(intellij_src)
    managers = ET.parse(Path(intellij_src) / "platform/platform-resources/src/DefaultColorSchemesManager.xml").getroot()
    default_el = [s for s in managers.findall("scheme") if s.get("name") == "Default"][0]
    default = Scheme(parse_attrs(default_el.find("attributes")), None, fallbacks)
    root = ET.parse(icls_path).getroot()
    assert root.get("parent_scheme") in (None, "Default"), "only Default-based schemes are modelled"
    return Scheme(parse_attrs(root.find("attributes")), default, fallbacks), default


def merge(under, above):
    """TextAttributes.merge"""
    if under is None:
        return above
    if above is None:
        return under
    r = dict(under)
    if above["bg"]:
        r["bg"] = above["bg"]
    if above["fg"]:
        r["fg"] = above["fg"]
    r["font"] = above["font"] | under["font"]
    if above["effect"] is not None and above["effect_color"]:
        r["effect"], r["effect_color"] = above["effect"], above["effect_color"]
    return r


INFO_ORDER = {  # higher = painted on top (HighlightInfoType severity / layer)
    "TODO_DEFAULT_ATTRIBUTES": 3, "DEPRECATED_ATTRIBUTES": 2, "MARKED_FOR_REMOVAL_ATTRIBUTES": 2,
    "REASSIGNED_LOCAL_VARIABLE_ATTRIBUTES": 1, "REASSIGNED_PARAMETER_ATTRIBUTES": 1,
}


def paint_intellij(source, spans, scheme):
    n = len(source)
    lexer = [None] * n
    infos = [[] for _ in range(n)]
    for s in spans:
        for c in range(s["start"], min(s["end"], n)):
            if s["layer"] == "lexer":
                lexer[c] = s           # later (more specific) lexer spans win, e.g. escapes inside strings
            else:
                infos[c].append(s)
    text_attrs = scheme.get("TEXT")
    out = []
    for c in range(n):
        layers = []
        syntax = None
        keys = []
        if lexer[c]:
            for k in lexer[c]["keys"]:
                syntax = merge(syntax, scheme.get(k))
            keys.append("+".join(lexer[c]["keys"]))
        stack = sorted(infos[c], key=lambda s: -INFO_ORDER.get(s["keys"][0], 0))
        for s in stack:
            a = scheme.get(s["keys"][0])
            if a:
                layers.append(a)
        if syntax:
            layers.append(syntax)
        fg = next((a["fg"] for a in layers if a["fg"]), None) or text_attrs["fg"]
        font = next((a["font"] for a in layers if a["font"]), 0)
        effect = next(((a["effect"], a["effect_color"]) for a in layers if a["effect"] is not None and a["effect_color"]), (None, None))
        why = " > ".join([s["keys"][0] for s in stack] + keys) or "TEXT"
        out.append({"fg": fg, "italic": bool(font & 2), "bold": bool(font & 1), "effect": effect[0],
                    "effect_color": effect[1], "why": why})
    return out


# ------------------------------------------------------------------ comparison

EFFECT_NAMES = {0: "box", 1: "underline", 2: "wave", 3: "strikethrough", 4: "bold underline", 5: "dotted"}


def vs_effect(ch):
    if ch.get("strikethrough"):
        return "strikethrough"
    if ch.get("squiggle"):
        return "wave"
    if ch.get("underline"):
        return "underline"
    return None


def style_key(fg, italic, bold, effect):
    return "%s%s%s%s" % (fg, " italic" if italic else "", " bold" if bold else "", (" " + effect) if effect else "")


def compare(source, vs_lines, ij_chars, ignore_brackets):
    rows = []
    offset = 0
    lines = source.split("\n")
    stats = Counter()
    groups = defaultdict(list)
    for ln, text in enumerate(lines):
        vs = vs_lines[ln]
        for c, ch in enumerate(text):
            o = offset + c
            if ch.isspace():
                continue
            v, i = vs[c], ij_chars[o]
            v_eff = vs_effect(v)
            i_eff = EFFECT_NAMES.get(i["effect"]) if i["effect"] is not None else None
            same = (v["fg"].upper() == i["fg"].upper() and bool(v["italic"]) == i["italic"] and bool(v["bold"]) == i["bold"]
                    and v_eff == i_eff)
            is_bracket = "bracket pair colorization" in v["why"]
            stats["chars"] += 1
            if same:
                stats["same"] += 1
            elif is_bracket and ignore_brackets:
                stats["bracket"] += 1
            else:
                stats["diff"] += 1
                key = (v["why"], i["why"], style_key(v["fg"], v["italic"], v["bold"], v_eff),
                       style_key(i["fg"], i["italic"], i["bold"], i_eff))
                groups[key].append((ln, c))
        offset += len(text) + 1
    return stats, groups


NAME_LABELS = {
    "CLASS_NAME_ATTRIBUTES": "Class", "ABSTRACT_CLASS_NAME_ATTRIBUTES": "Abstract class",
    "ANONYMOUS_CLASS_NAME_ATTRIBUTES": "Anonymous class (base type)", "INTERFACE_NAME_ATTRIBUTES": "Interface",
    "ENUM_NAME_ATTRIBUTES": "Enum", "RECORD_NAME_ATTRIBUTES": "Record", "ANNOTATION_NAME_ATTRIBUTES": "Annotation",
    "TYPE_PARAMETER_NAME_ATTRIBUTES": "Type parameter", "ANNOTATION_ATTRIBUTE_NAME_ATTRIBUTES": "Annotation attribute",
    "METHOD_DECLARATION_ATTRIBUTES": "Method declaration", "METHOD_CALL_ATTRIBUTES": "Method call",
    "STATIC_METHOD_ATTRIBUTES": "Static method call", "STATIC_METHOD_IMPORTED_ATTRIBUTES": "Static method, statically imported",
    "ABSTRACT_METHOD_ATTRIBUTES": "Abstract / interface method call", "INHERITED_METHOD_ATTRIBUTES": "Inherited method call",
    "CONSTRUCTOR_DECLARATION_ATTRIBUTES": "Constructor declaration", "CONSTRUCTOR_CALL_ATTRIBUTES": "Constructor call (new)",
    "INSTANCE_FIELD_ATTRIBUTES": "Instance field", "INSTANCE_FINAL_FIELD_ATTRIBUTES": "Instance final field",
    "STATIC_FIELD_ATTRIBUTES": "Static field", "STATIC_FIELD_IMPORTED_ATTRIBUTES": "Static field, statically imported",
    "STATIC_FINAL_FIELD_ATTRIBUTES": "Static final field (constant)", "STATIC_FINAL_FIELD_IMPORTED_ATTRIBUTES": "Constant, statically imported",
    "RECORD_COMPONENT_ATTRIBUTES": "Record component", "LOCAL_VARIABLE_ATTRIBUTES": "Local variable",
    "PARAMETER_ATTRIBUTES": "Parameter (method, catch, pattern)", "LAMBDA_PARAMETER_ATTRIBUTES": "Lambda parameter",
    "IMPLICIT_ANONYMOUS_CLASS_PARAMETER_ATTRIBUTES": "Variable captured by lambda / anonymous class",
}
DECORATIONS = {"REASSIGNED_LOCAL_VARIABLE_ATTRIBUTES", "REASSIGNED_PARAMETER_ATTRIBUTES", "DEPRECATED_ATTRIBUTES",
               "MARKED_FOR_REMOVAL_ATTRIBUTES", "TODO_DEFAULT_ATTRIBUTES"}
PRIMITIVES = {"boolean", "byte", "char", "short", "int", "long", "float", "double", "void"}


def element_label(span, text, vs_why):
    key = span["keys"][-1] if span["layer"] == "lexer" else span["keys"][0]
    why = span["why"]
    if span["layer"] == "info":
        if why == "package":
            return "Package name"
        if key == "STATIC_FINAL_FIELD_ATTRIBUTES" and "enumMember" in vs_why:
            return "Enum constant"
        if key == "TODO_DEFAULT_ATTRIBUTES":
            return "TODO comment"
        if key == "DEPRECATED_ATTRIBUTES":
            return "Deprecated API use"
        if key == "JAVA_KEYWORD":
            return "Contextual keyword (%s)" % ("var" if text == "var" else "when" if text == "when" else "record, sealed, permits, yield")
        if key in REASSIGNED_KEYS:
            return None
        label = NAME_LABELS.get(key, key)
        return label + (" (in Javadoc)" if why.startswith("javadoc") else "")
    if key == "JAVA_KEYWORD":
        if text in ("true", "false", "null"):
            return "Literal keyword (true, false, null)"
        if text in ("this", "super", "instanceof"):
            return "Keyword: " + text
        if text in PRIMITIVES:
            return "Primitive type"
        return "Keyword / modifier"
    return {
        "JAVA_STRING": "String / char / text block", "JAVA_VALID_STRING_ESCAPE": "String escape",
        "JAVA_NUMBER": "Number", "JAVA_LINE_COMMENT": "Line comment", "JAVA_BLOCK_COMMENT": "Block comment",
        "JAVA_DOC_COMMENT": "Javadoc text", "JAVA_DOC_TAG": "Javadoc tag", "JAVA_DOC_MARKUP": "Javadoc HTML",
        "JAVA_OPERATION_SIGN": "Generic angle bracket" if "angle" in vs_why else "Operator",
        "JAVA_COMMA": "Comma", "JAVA_DOT": "Dot", "JAVA_SEMICOLON": "Semicolon",
        "JAVA_PARENTH": "Brackets ( ) [ ] { }", "JAVA_BRACKETS": "Brackets ( ) [ ] { }", "JAVA_BRACES": "Brackets ( ) [ ] { }",
    }.get(key, key)


REASSIGNED_KEYS = {"REASSIGNED_LOCAL_VARIABLE_ATTRIBUTES", "REASSIGNED_PARAMETER_ATTRIBUTES"}


def element_table(source, spans, vs_lines, ij_chars):
    """One row per kind of Java element: how many occurrences paint identically in both editors."""
    starts = [0]
    for l in source.split("\n"):
        starts.append(starts[-1] + len(l) + 1)

    def vs_at(o):
        import bisect
        ln = bisect.bisect_right(starts, o) - 1
        return vs_lines[ln][o - starts[ln]]

    def same(o):
        v, i = vs_at(o), ij_chars[o]
        i_eff = EFFECT_NAMES.get(i["effect"]) if i["effect"] is not None else None
        return (v["fg"].upper() == i["fg"].upper() and bool(v["italic"]) == i["italic"] and bool(v["bold"]) == i["bold"]
                and vs_effect(v) == i_eff)

    rows = defaultdict(lambda: {"total": 0, "same": 0, "examples": [], "vs": Counter(), "ij": Counter()})
    covered_by_name = set()
    for s in spans:
        if s["layer"] == "info" and s["keys"][0] not in DECORATIONS:
            covered_by_name.update(range(s["start"], s["end"]))
    seen = set()
    for s in spans:
        k = (s["start"], s["end"], s["layer"])
        if k in seen or (s["layer"] == "info" and s["keys"][0] in REASSIGNED_KEYS):
            continue
        seen.add(k)
        if s["layer"] == "lexer" and (s["keys"][-1] == "JAVA_DOC_COMMENT" or s["start"] in covered_by_name):
            continue  # whole doc comments are summarised by their parts; names are counted by the names layer
        text = source[s["start"]:s["end"]]
        positions = [o for o in range(s["start"], s["end"]) if not source[o].isspace()]
        if not positions:
            continue
        label = element_label(s, text, vs_at(positions[0])["why"])
        if not label:
            continue
        r = rows[label]
        r["total"] += 1
        ok = all(same(o) for o in positions)
        r["same"] += ok
        v, i = vs_at(positions[0]), ij_chars[positions[0]]
        r["vs"][style_key(v["fg"], v["italic"], v["bold"], vs_effect(v)) + " | " + v["why"]] += 1
        r["ij"][style_key(i["fg"], i["italic"], i["bold"], EFFECT_NAMES.get(i["effect"]) if i["effect"] is not None else None)
                + " | " + i["why"]] += 1
        if len(r["examples"]) < 4 and text.strip() not in r["examples"]:
            r["examples"].append(text.strip()[:40])
    return rows


ELEMENT_ORDER = [
    "Class", "Abstract class", "Interface", "Enum", "Record", "Annotation", "Anonymous class (base type)", "Type parameter",
    "Package name", "Constructor declaration", "Constructor call (new)", "Method declaration", "Method call",
    "Static method call", "Static method, statically imported", "Abstract / interface method call", "Inherited method call",
    "Annotation attribute", "Instance field", "Instance final field", "Static field", "Static field, statically imported",
    "Static final field (constant)", "Constant, statically imported", "Enum constant", "Record component", "Local variable",
    "Parameter (method, catch, pattern)", "Lambda parameter", "Variable captured by lambda / anonymous class",
    "Keyword / modifier", "Primitive type", "Keyword: this", "Keyword: super", "Keyword: instanceof",
    "Literal keyword (true, false, null)", "Contextual keyword (record, sealed, permits, yield)", "Contextual keyword (var)",
    "Contextual keyword (when)", "String / char / text block", "String escape", "Number", "Operator", "Generic angle bracket",
    "Comma", "Dot", "Semicolon", "Brackets ( ) [ ] { }", "Line comment", "Block comment", "Javadoc tag", "Javadoc HTML",
    "TODO comment", "Deprecated API use",
]


def ordered_elements(elements):
    def rank(label):
        base = label.replace(" (in Javadoc)", "")
        return (ELEMENT_ORDER.index(base) if base in ELEMENT_ORDER else len(ELEMENT_ORDER), label)
    return sorted(elements.items(), key=lambda kv: rank(kv[0]))


def elements_markdown(elements):
    out = ["| Java element | Examples | Identical | VS Code | IntelliJ key |", "|---|---|---|---|---|"]
    for label, r in ordered_elements(elements):
        vs_top = r["vs"].most_common(1)[0][0].split(" | ")[0]
        ij = r["ij"].most_common(1)[0][0].split(" | ")
        mark = "✅" if r["same"] == r["total"] else ("⚠️" if r["same"] else "❌")
        key = ij[1].split(" > ")[0].replace("+", " + ")
        out.append("| %s | %s | %s %d/%d | `%s` | `%s` |" % (label, ", ".join("`%s`" % e.replace("|", "\\|") for e in r["examples"][:3]),
                                                           mark, r["same"], r["total"], vs_top, key))
    return "\n".join(out)


def token_text(lines, positions):
    """Collapse adjacent char positions into token snippets."""
    out = []
    prev = None
    for ln, c in positions:
        if prev and prev[0] == ln and prev[1] + 1 == c:
            out[-1] = (out[-1][0], out[-1][1] + lines[ln][c])
        else:
            out.append((ln + 1, lines[ln][c]))
        prev = (ln, c)
    return out


# ------------------------------------------------------------------ HTML


def span_html(text, fg, italic, bold, effect, effect_color, title):
    style = "color:%s;" % fg
    if italic:
        style += "font-style:italic;"
    if bold:
        style += "font-weight:bold;"
    if effect == "strikethrough":
        style += "text-decoration:line-through;text-decoration-color:%s;" % effect_color
    elif effect == "wave":
        style += "text-decoration:underline wavy;text-decoration-color:%s;text-decoration-skip-ink:none;" % effect_color
    elif effect == "underline":
        style += "text-decoration:underline;text-decoration-color:%s;" % effect_color
    return '<span style="%s" title="%s">%s</span>' % (style, html.escape(title, quote=True), html.escape(text))


def render_code(lines, style_at):
    out = []
    for ln, text in enumerate(lines):
        buf = []
        cur = None
        for c, ch in enumerate(text):
            st = style_at(ln, c)
            if cur and cur[0] == st:
                cur[1] += ch
            else:
                cur = [st, ch]
                buf.append(cur)
        line_html = "".join(span_html(t, *st) for st, t in buf)
        out.append('<div class="ln"><span class="no">%d</span>%s</div>' % (ln + 1, line_html or "&#8203;"))
    return "".join(out)  # no newlines between the line divs: they would render as extra lines inside <pre>


def write_report(path, source, vs_lines, ij_chars, stats, groups, theme_colors, notes, elements):
    lines = source.split("\n")
    starts = [0]
    for l in lines:
        starts.append(starts[-1] + len(l) + 1)

    def vs_style(ln, c):
        ch = vs_lines[ln][c]
        eff = vs_effect(ch)
        color = {"strikethrough": ch["fg"], "wave": {"warning": theme_colors["editorWarning.foreground"],
                                                      "info": theme_colors["editorInfo.foreground"],
                                                      "error": theme_colors["editorError.foreground"]}.get(ch.get("squiggle"), ch["fg"]),
                 "underline": ch["fg"]}.get(eff)
        if eff == "strikethrough" and ch.get("squiggle"):
            color = ch["fg"]
        return (ch["fg"], bool(ch["italic"]), bool(ch["bold"]), eff, color, ch["why"])

    def ij_style(ln, c):
        ch = ij_chars[starts[ln] + c]
        eff = EFFECT_NAMES.get(ch["effect"]) if ch["effect"] is not None else None
        return (ch["fg"], ch["italic"], ch["bold"], eff, ch["effect_color"], ch["why"])

    rows = []
    for (vwhy, iwhy, vst, ist), pos in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        toks = token_text(lines, pos)
        examples = ", ".join("<code>%s</code> <small>L%d</small>" % (html.escape(t), l) for l, t in toks[:6])
        rows.append("<tr><td>%d</td><td>%s</td><td><span class=sw style='background:%s'></span>%s<br><small>%s</small></td>"
                    "<td><span class=sw style='background:%s'></span>%s<br><small>%s</small></td></tr>"
                    % (len(toks), examples, vst.split()[0], html.escape(vst), html.escape(vwhy),
                       ist.split()[0], html.escape(ist), html.escape(iwhy)))
    element_rows = []
    for label, r in ordered_elements(elements):
        vs_top = r["vs"].most_common(1)[0][0].split(" | ")
        ij_top = r["ij"].most_common(1)[0][0].split(" | ")
        mark = "&#10003;" if r["same"] == r["total"] else ("~" if r["same"] else "&#10007;")
        element_rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td><b>%s</b> %d/%d</td>"
                            "<td><span class=sw style='background:%s'></span>%s<br><small>%s</small></td>"
                            "<td><span class=sw style='background:%s'></span>%s<br><small>%s</small></td></tr>"
                            % (html.escape(label), ", ".join("<code>%s</code>" % html.escape(e) for e in r["examples"]), "",
                               mark, r["same"], r["total"], vs_top[0].split()[0], html.escape(vs_top[0]), html.escape(vs_top[1]),
                               ij_top[0].split()[0], html.escape(ij_top[0]), html.escape(ij_top[1])))
    pct = 100.0 * stats["same"] / max(1, stats["chars"])
    doc = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Earl Grey: VS Code vs IntelliJ</title>
<style>
:root{--bg:#FCFBF9;--panel:#F7F3EE;--fg:#605A52;--muted:#7F7A73;--line:#DDDBD8}
body{margin:0;background:var(--panel);color:var(--fg);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1500px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px} h2{font-size:17px;margin:28px 0 8px}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}.stat{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 14px}
.stat b{display:block;font-size:20px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:1000px){.cols{grid-template-columns:1fr}}
.pane{background:var(--bg);border:1px solid var(--line);border-radius:8px;overflow:auto}
.pane h3{margin:0;padding:8px 12px;font-size:13px;border-bottom:1px solid var(--line);color:var(--muted);position:sticky;top:0;background:var(--bg)}
pre{margin:0;padding:8px 0;font:13px/1.55 "JetBrains Mono",Menlo,Consolas,monospace}
.ln{white-space:pre;padding-right:12px}.no{display:inline-block;width:3.2em;text-align:right;margin-right:1.2em;color:#CDCBC7}
.ln.diff{background:#F4F0F1}
table{border-collapse:collapse;width:100%;background:var(--bg);border:1px solid var(--line)}
td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{font-size:12px;color:var(--muted)} code{font:12px "JetBrains Mono",Menlo,monospace}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:middle;border:1px solid #0002}
small{color:var(--muted)} ul{margin:6px 0 0 18px;padding:0}
</style></head><body><main>
<h1>Earl Grey &mdash; VS Code vs IntelliJ, character by character</h1>
<p>Left: what VS Code (Red Hat Java + Earl Grey) paints. Right: what IntelliJ paints with <code>Earl Grey.icls</code>. Hover any token for the rule that colored it.</p>
<div class="stats"><div class="stat"><b>{PCT}</b>identical characters</div><div class="stat"><b>{CHARS}</b>non-blank characters</div>
<div class="stat"><b>{DIFF}</b>different (tokens below)</div><div class="stat"><b>{BRACKETS}</b>brackets (VS Code bracket-pair colors)</div></div>
<h2>Every kind of Java element</h2>
<table><tr><th>Element</th><th>Examples</th><th></th><th>Identical</th><th>VS Code</th><th>IntelliJ</th></tr>{ELEMENTS}</table>
<h2>Known differences IntelliJ cannot express</h2><ul>{NOTES}</ul>
<h2>Every remaining difference</h2>
<table><tr><th>#</th><th>Tokens</th><th>VS Code</th><th>IntelliJ</th></tr>{ROWS}</table>
<h2>Side by side</h2>
<div class="cols"><div class="pane"><h3>VS Code</h3><pre>{VSCODE}</pre></div><div class="pane"><h3>IntelliJ IDEA</h3><pre>{INTELLIJ}</pre></div></div>
</main></body></html>"""
    for k, v in {"{PCT}": "%.1f%%" % pct, "{CHARS}": str(stats["chars"]), "{DIFF}": str(stats["diff"]),
                 "{BRACKETS}": str(stats["bracket"]), "{NOTES}": "".join("<li>%s</li>" % n for n in notes),
                 "{ROWS}": "".join(rows), "{ELEMENTS}": "".join(element_rows), "{VSCODE}": render_code(lines, vs_style),
                 "{INTELLIJ}": render_code(lines, ij_style)}.items():
        doc = doc.replace(k, v)
    Path(path).write_text(doc, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheme", required=True)
    ap.add_argument("--intellij-spans", required=True)
    ap.add_argument("--vscode", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--intellij-src", required=True)
    ap.add_argument("--theme", required=True, help="the VS Code theme json (for diagnostic colors)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--json-out")
    ap.add_argument("--markdown-out", help="write the per-element table as Markdown")
    args = ap.parse_args()

    source = Path(args.source).read_text(encoding="utf-8")
    scheme, _ = load_schemes(args.scheme, args.intellij_src)
    spans = json.loads(Path(args.intellij_spans).read_text())["spans"]
    vs = json.loads(Path(args.vscode).read_text())
    assert vs["text"] == source.split("\n"), "VS Code render is for a different source"
    ij = paint_intellij(source, spans, scheme)
    stats, groups = compare(source, vs["lines"], ij, ignore_brackets=True)

    theme_text = Path(args.theme).read_text(encoding="utf-8")
    theme_colors = {k: v for k, v in re.findall(r'"(editor(?:Warning|Info|Error)\.foreground)":\s*"(#[0-9A-Fa-f]{6})', theme_text)}
    notes = [
        "Packages (<code>java.util.</code>): IntelliJ highlights package names with the <b>class name</b> key (HighlightNamesUtil.highlightPackage), so they share the class color. VS Code paints namespaces #886A44.",
        "Enum constants: IntelliJ treats them as <b>static final fields</b>; VS Code gives the <code>enumMember</code> token the class style (#605A52 italic). The scheme keeps static final fields correct.",
        "<code>true</code>/<code>false</code>/<code>null</code>, <code>super(...)</code>, <code>instanceof</code>, <code>var</code>, <code>when</code>: one <code>JAVA_KEYWORD</code> key in IntelliJ, several TextMate scopes in VS Code.",
        "<code>-&gt;</code>, <code>::</code>, <code>@</code>, <code>...</code> and string quote marks have no attributes key of their own in IntelliJ.",
        "Bracket pair colorization is an editor feature in VS Code (on by default). IntelliJ needs the Rainbow Brackets (Lite) plugin; the scheme ships its color keys.",
    ]
    elements = element_table(source, spans, vs["lines"], ij)
    write_report(args.out, source, vs["lines"], ij, stats, groups, theme_colors, notes, elements)
    if args.markdown_out:
        Path(args.markdown_out).write_text(elements_markdown(elements) + "\n", encoding="utf-8")
    summary = {"stats": dict(stats), "groups": [
        {"count": len(token_text(source.split("\n"), pos)), "vscode_rule": k[0], "intellij_rule": k[1], "vscode": k[2], "intellij": k[3],
         "tokens": [t for _, t in token_text(source.split("\n"), pos)][:12]}
        for k, pos in sorted(groups.items(), key=lambda kv: -len(kv[1]))]}
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["stats"]))
    for g in summary["groups"]:
        print("%3d  VS %-30s IJ %-30s | %s\n      vs-why: %s\n      ij-why: %s" % (g["count"], g["vscode"], g["intellij"], " ".join(g["tokens"][:8]), g["vscode_rule"], g["intellij_rule"]))


if __name__ == "__main__":
    main()
