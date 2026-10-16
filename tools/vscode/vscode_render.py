"""Reproduce what VS Code (with Red Hat's Java extension) paints for every character of a Java file.

Inputs
  textmate.json  - per-line TextMate tokens + resolved TextMate styles (from tokenize.js / vscode-textmate)
  semtokens.json - jdt.ls semantic tokens (legend + data) and diagnostics
  theme.json     - the VS Code color theme (Earl Grey)

The semantic-token resolution is a direct port of
  src/vs/workbench/services/themes/common/colorThemeData.ts   (getTokenStyle, resolveScopes)
  src/vs/platform/theme/common/tokenClassificationRegistry.ts (type hierarchy, selector scoring, default rules)
plus the semanticTokenTypes / semanticTokenScopes contributed by redhat.java's package.json.
"""
import json
import re
import sys

# ---------------------------------------------------------------- theme loading


def read_jsonc(path):
    text = open(path, encoding="utf-8").read()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    text = re.sub(r",(\s*[\]}])", r"\1", text)
    return json.loads(text)


def style_from_settings(foreground=None, font_style=None, bold=None, underline=None, strikethrough=None, italic=None):
    """TokenStyle.fromSettings"""
    if font_style is not None:
        bold = italic = underline = strikethrough = False
        for m in re.finditer(r"italic|bold|underline|strikethrough", font_style):
            if m.group(0) == "bold":
                bold = True
            elif m.group(0) == "italic":
                italic = True
            elif m.group(0) == "underline":
                underline = True
            else:
                strikethrough = True
    return {"foreground": foreground.upper() if foreground else None, "bold": bold, "underline": underline,
            "strikethrough": strikethrough, "italic": italic}


# ---------------------------------------------------------------- TextMate scope matching (resolveScopes)


def scopes_are_matching(this_scope, scope_name):
    if not this_scope:
        return False
    if this_scope == scope_name:
        return True
    n = len(scope_name)
    return len(this_scope) > n and this_scope[:n] == scope_name and this_scope[n] == "."


def name_matcher(identifiers, scopes):
    if len(scopes) < len(identifiers):
        return -1
    score = None
    for identifier in identifiers:
        found = False
        for i in range(len(scopes) - 1, -1, -1):
            if scopes_are_matching(scopes[i], identifier):
                score = (i + 1) * 0x10000 + len(identifier)
                found = True
                break
        if not found:
            return -1
    return score if score is not None else -1


def rule_matcher(rule):
    scope = rule.get("scope")
    if not scope or not rule.get("settings"):
        return lambda probe: -1
    selectors = scope if isinstance(scope, list) else [scope]
    alternatives = []
    for sel in selectors:
        for part in sel.split(","):
            idents = part.split()
            if idents:
                alternatives.append(idents)
    return lambda probe: max([name_matcher(a, probe) for a in alternatives] or [-1])


class Theme:
    def __init__(self, path):
        self.data = read_jsonc(path)
        self.token_colors = [r for r in self.data.get("tokenColors", [])]
        self.matchers = [rule_matcher(r) for r in self.token_colors]
        self.semantic_rules = []
        for key, value in self.data.get("semanticTokenColors", {}).items():
            rule = read_semantic_token_rule(key, value)
            if rule:
                self.semantic_rules.append(rule)
            else:
                self.ignored_semantic_rules = getattr(self, "ignored_semantic_rules", []) + [key]

    def resolve_scopes(self, probe_list):
        for probe in probe_list:
            foreground = font_style = None
            fg_score = fs_score = -1
            fg_rule = None
            for rule, matcher in zip(self.token_colors, self.matchers):
                score = matcher(probe)
                if score >= 0:
                    settings = rule["settings"]
                    if score >= fg_score and settings.get("foreground"):
                        foreground, fg_score, fg_rule = settings["foreground"], score, rule
                    if score >= fs_score and isinstance(settings.get("fontStyle"), str):
                        font_style, fs_score = settings["fontStyle"], score
            if foreground is not None or font_style is not None:
                return style_from_settings(foreground, font_style), (probe, fg_rule.get("name") if fg_rule else None)
        return None, None


# ---------------------------------------------------------------- semantic token classification registry

TYPE_SUPER = {
    # VS Code built-ins
    "member": "method",
    # redhat.java package.json "semanticTokenTypes"
    "annotation": "type",
    "annotationMember": "method",
    "modifier": "keyword",
    "record": "class",
    "recordComponent": "parameter",
}


def hierarchy(t):
    h = [t]
    while t in TYPE_SUPER:
        t = TYPE_SUPER[t]
        h.append(t)
    return h


def parse_selector(s, language=None):
    """parseClassifierString + parseTokenSelector"""
    lang = language
    if ":" in s:
        s, lang = s.split(":", 1)
    parts = s.split(".")
    return {"type": parts[0], "modifiers": parts[1:], "language": lang, "text": s}


def selector_match(sel, type_, modifiers, language):
    score = 0
    if sel["language"] is not None:
        if sel["language"] != language:
            return -1
        score += 10
    if sel["type"] != "*":
        h = hierarchy(type_)
        if sel["type"] not in h:
            return -1
        score += 100 - h.index(sel["type"])
    for m in sel["modifiers"]:
        if m not in modifiers:
            return -1
    return score + len(sel["modifiers"]) * 100


def read_semantic_token_rule(selector, settings):
    if isinstance(settings, str):
        return {"selector": parse_selector(selector), "style": style_from_settings(settings)}
    if isinstance(settings, dict) and (isinstance(settings.get("foreground"), str) or isinstance(settings.get("fontStyle"), str)
                                       or any(isinstance(settings.get(k), bool) for k in ("italic", "bold", "underline", "strikethrough"))):
        return {"selector": parse_selector(selector),
                "style": style_from_settings(settings.get("foreground"), settings.get("fontStyle"), settings.get("bold"),
                                             settings.get("underline"), settings.get("strikethrough"), settings.get("italic"))}
    return None  # e.g. Earl Grey's misspelled "forground" entries are dropped here


# registration order matters only for ties; it mirrors tokenClassificationRegistry.ts then the extension point
DEFAULT_RULES = [
    ("comment", [["comment"]]), ("string", [["string"]]), ("keyword", [["keyword.control"]]),
    ("number", [["constant.numeric"]]), ("regexp", [["constant.regexp"]]), ("operator", [["keyword.operator"]]),
    ("namespace", [["entity.name.namespace"]]),
    ("type", [["entity.name.type"], ["support.type"]]), ("struct", [["entity.name.type.struct"]]),
    ("class", [["entity.name.type.class"], ["support.class"]]), ("interface", [["entity.name.type.interface"]]),
    ("enum", [["entity.name.type.enum"]]), ("typeParameter", [["entity.name.type.parameter"]]),
    ("function", [["entity.name.function"], ["support.function"]]),
    ("method", [["entity.name.function.member"], ["support.function"]]),
    ("macro", [["entity.name.function.preprocessor"]]),
    ("variable", [["variable.other.readwrite"], ["entity.name.variable"]]), ("parameter", [["variable.parameter"]]),
    ("property", [["variable.other.property"]]), ("enumMember", [["variable.other.enummember"]]),
    ("event", [["variable.other.event"]]), ("decorator", [["entity.name.decorator"], ["entity.name.function"]]),
    ("variable.readonly", [["variable.other.constant"]]), ("property.readonly", [["variable.other.constant.property"]]),
    ("type.defaultLibrary", [["support.type"]]), ("class.defaultLibrary", [["support.class"]]),
    ("interface.defaultLibrary", [["support.class"]]),
    ("variable.defaultLibrary", [["support.variable"], ["support.other.variable"]]),
    ("variable.defaultLibrary.readonly", [["support.constant"]]),
    ("property.defaultLibrary", [["support.variable.property"]]),
    ("property.defaultLibrary.readonly", [["support.constant.property"]]),
    ("function.defaultLibrary", [["support.function"]]), ("member.defaultLibrary", [["support.function"]]),
]
# redhat.java contributes "semanticTokenScopes" for language "java"
JAVA_RULES = {
    "annotation": ["storage.type.annotation.java"],
    "decorator": ["storage.type.annotation.java"],
    "annotationMember": ["entity.name.annotationMember.java", "constant.other.key.java"],
    "modifier": ["storage.modifier.java"],
    "keyword.documentation": ["keyword.other.documentation.javadoc.java"],
    "*.constructor": ["entity.name.function.java"],
}
DEFAULT_SELECTORS = [(parse_selector(s), probes) for s, probes in DEFAULT_RULES] + \
                    [(parse_selector(s, "java"), [p.split(" ") for p in probes]) for s, probes in JAVA_RULES.items()]

PROPS = ("foreground", "bold", "underline", "strikethrough", "italic")


def get_token_style(theme, type_, modifiers, language="java"):
    result = {p: None for p in PROPS}
    score = {p: -1 for p in PROPS}
    source = {}

    def process(match_score, style, definition):
        if style["foreground"] and score["foreground"] <= match_score:
            score["foreground"] = match_score
            result["foreground"] = style["foreground"]
            source["foreground"] = definition
        for p in ("bold", "underline", "strikethrough", "italic"):
            if style[p] is not None and score[p] <= match_score:
                score[p] = match_score
                result[p] = style[p]
                source[p] = definition

    for rule in theme.semantic_rules:
        s = selector_match(rule["selector"], type_, modifiers, language)
        if s >= 0:
            process(s, rule["style"], "semanticTokenColors." + rule["selector"]["text"])
    undefined = any(score[p] == -1 for p in PROPS)
    for p in PROPS:
        if score[p] != -1:
            score[p] = float("inf")
    if undefined:
        for sel, probes in DEFAULT_SELECTORS:
            s = selector_match(sel, type_, modifiers, language)
            if s >= 0:
                style, how = theme.resolve_scopes(probes)
                if style:
                    process(s, style, "default " + sel["text"] + (":" + sel["language"] if sel["language"] else "") + " -> " + " ".join(how[0]))
    return result, source


# ---------------------------------------------------------------- per-character composition


def decode_semantic(sem, lines, rename=None):
    legend = sem["legend"]
    rename = rename or {}
    out = []
    line = col = 0
    data = sem["data"]
    for i in range(0, len(data), 5):
        dl, dc, length, t, mods = data[i:i + 5]
        if dl:
            line += dl
            col = dc
        else:
            col += dc
        type_ = legend["tokenTypes"][t]
        type_ = rename.get(type_, type_)
        modifiers = [m for b, m in enumerate(legend["tokenModifiers"]) if mods & (1 << b)]
        out.append({"line": line, "start": col, "end": col + length, "type": type_, "modifiers": modifiers,
                    "text": lines[line][col:col + length]})
    return out


BRACKET_COLORS_KEYS = ["editorBracketHighlight.foreground%d" % i for i in range(1, 7)]
OPEN, CLOSE = "([{", ")]}"


def is_string_or_comment(scopes):
    # vscode-textmate's toStandardTokenType: comment | string | regex | meta.embedded
    return any(re.search(r"\b(comment|string|regex)\b", s) for s in scopes)


def render(textmate, sem_tokens, diagnostics, theme, bracket_colorization=True):
    """Returns per-line list of char styles: dict(fg, italic, bold, underline, strikethrough, why)."""
    lines = []
    for entry in textmate:
        chars = []
        scope_of = [None] * len(entry["text"])
        for t in entry["tokens"]:
            for c in range(t["start"], t["end"]):
                scope_of[c] = t["scopes"]
        for st in entry["styles"]:
            for c in range(st["start"], st["end"]):
                scopes = scope_of[c] or []
                chars.append({"fg": st["fg"], "italic": st["italic"], "bold": st["bold"], "underline": st["underline"],
                              "strikethrough": st["strikethrough"], "scopes": scopes, "layer": "textmate",
                              "why": "textmate " + (scopes[-1] if scopes else "")})
        lines.append(chars)
    # semantic tokens override per property
    for tok in sem_tokens:
        style, source = get_token_style(theme, tok["type"], tok["modifiers"])
        tok["style"] = style
        tok["source"] = source
        for c in range(tok["start"], tok["end"]):
            ch = lines[tok["line"]][c]
            if style["foreground"]:
                ch["fg"] = style["foreground"]
            for p in ("italic", "bold", "underline", "strikethrough"):
                if style[p] is not None:
                    ch[p] = style[p]
            ch["layer"] = "semantic"
            ch["why"] = "semantic %s%s" % (tok["type"], "".join("." + m for m in tok["modifiers"]))
    # diagnostics: Deprecated tag -> line-through, Unnecessary tag -> faded, info/warning/error -> squiggle
    for d in diagnostics:
        r = d["range"]
        for ln in range(r["start"]["line"], r["end"]["line"] + 1):
            a = r["start"]["character"] if ln == r["start"]["line"] else 0
            b = r["end"]["character"] if ln == r["end"]["line"] else len(lines[ln])
            for c in range(a, b):
                ch = lines[ln][c]
                if 2 in d.get("tags", []):
                    ch["strikethrough"] = True
                if 1 in d.get("tags", []):
                    ch["faded"] = True
                ch["squiggle"] = {1: "error", 2: "warning", 3: "info", 4: "hint"}[d.get("severity", 1)]
    # bracket pair colorization (editor.bracketPairColorization.enabled defaults to true)
    if bracket_colorization:
        colors = [theme.data["colors"][k].upper() for k in BRACKET_COLORS_KEYS]
        depth = 0
        for ln, entry in enumerate(textmate):
            text = entry["text"]
            for c, chr_ in enumerate(text):
                ch = lines[ln][c]
                if is_string_or_comment(ch["scopes"]):
                    continue
                if chr_ in OPEN:
                    ch["fg"] = colors[depth % 6]
                    ch["why"] = "bracket pair colorization, level %d" % (depth + 1)
                    ch["bracket_level"] = depth
                    depth += 1
                elif chr_ in CLOSE:
                    depth = max(depth - 1, 0)
                    ch["fg"] = colors[depth % 6]
                    ch["why"] = "bracket pair colorization, level %d" % (depth + 1)
                    ch["bracket_level"] = depth
    return lines


if __name__ == "__main__":
    textmate_path, sem_path, theme_path, out_path = sys.argv[1:5]
    theme = Theme(theme_path)
    textmate = json.load(open(textmate_path))
    sem = json.load(open(sem_path))
    text_lines = [e["text"] for e in textmate]
    # jdt.ls >= 1.60 reports annotations as the standard "decorator" type (eclipse-jdtls/eclipse.jdt.ls#3788)
    sem_tokens = decode_semantic(sem, text_lines, rename={"annotation": "decorator"})
    lines = render(textmate, sem_tokens, sem["diagnostics"], theme)
    json.dump({"lines": [[{k: v for k, v in ch.items() if k != "scopes"} for ch in l] for l in lines],
               "text": text_lines, "semantic": sem_tokens,
               "ignored_semantic_rules": getattr(theme, "ignored_semantic_rules", [])}, open(out_path, "w"), indent=0)
    print("ignored semanticTokenColors entries:", getattr(theme, "ignored_semantic_rules", []))
    # summary of distinct semantic styles
    seen = {}
    for t in sem_tokens:
        k = t["type"] + "".join("." + m for m in sorted(t["modifiers"]) if m not in ("public", "private", "protected", "generic", "typeArgument", "importDeclaration", "declaration"))
        seen.setdefault(k, (t["style"], t["source"], t["text"]))
    for k in sorted(seen):
        s, src, text = seen[k]
        print("%-40s fg=%s italic=%s  e.g. %-14s via %s" % (k, s["foreground"], s["italic"], text, src.get("foreground")))
