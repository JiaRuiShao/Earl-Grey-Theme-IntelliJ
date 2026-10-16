"""Checks a built Earl Grey UI Theme jar before it is released.

    python3 tools/validate-plugin.py build/EarlGreyTheme-1.2.0.jar [expected-version]

Fails (exit 1) when:
  * plugin.xml is malformed, has the wrong id, or a version other than the expected one;
  * the theme JSON's editorScheme or any icon it maps is missing from the jar;
  * the editor scheme is not named "EarlGrey" (the name published releases use; users' selection is stored under it);
  * the scheme carries an "originalScheme" property (it makes imported copies borrow this scheme's label);
  * the scheme uses an attributes key IntelliJ does not define (1.1.0 shipped 14 such keys, so those Java
    elements silently fell back to other colors) - see tools/intellij-keys.txt;
  * the Parity license text is missing (the license requires every copy to carry it).
"""
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

PLUGIN_ID = "wtf.halt.earlgrey.theme"
SCHEME_NAME = "EarlGrey"


def main():
    jar_path = sys.argv[1]
    expected_version = sys.argv[2] if len(sys.argv) > 2 else None
    known = {line.strip() for line in (Path(__file__).parent / "intellij-keys.txt").read_text().splitlines()
             if line.strip() and not line.startswith("#")}
    errors = []
    jar = zipfile.ZipFile(jar_path)
    names = set(jar.namelist())

    plugin = ET.fromstring(jar.read("META-INF/plugin.xml"))
    if plugin.findtext("id") != PLUGIN_ID:
        errors.append("plugin id is %r, expected %r" % (plugin.findtext("id"), PLUGIN_ID))
    version = plugin.findtext("version")
    if expected_version and version != expected_version:
        errors.append("plugin version is %r, expected %r" % (version, expected_version))
    providers = plugin.findall("extensions/themeProvider")
    if len(providers) != 1:
        errors.append("expected exactly one themeProvider, found %d" % len(providers))
    if plugin.findall("extensions/bundledColorScheme"):
        errors.append("bundledColorScheme registers the scheme a second time (the theme JSON already does)")
    if "META-INF/LICENSE-PARITY.md" not in names:
        errors.append("META-INF/LICENSE-PARITY.md is missing")

    theme_path = providers[0].get("path").lstrip("/") if providers else ""
    theme = json.loads(jar.read(theme_path))
    scheme_path = theme.get("editorScheme", "").lstrip("/")
    if scheme_path not in names:
        errors.append("editorScheme %r is not in the jar" % scheme_path)

    def icon_targets(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "ColorPalette":
                    continue
                if isinstance(v, str) and v.endswith(".svg"):
                    yield v
                else:
                    yield from icon_targets(v)
    for target in sorted(set(icon_targets(theme.get("icons", {})))):
        if target.lstrip("/") not in names:
            errors.append("icon %s mapped in the theme JSON is not in the jar" % target)

    if scheme_path in names:
        scheme = ET.fromstring(jar.read(scheme_path))
        if scheme.get("name") != SCHEME_NAME:
            errors.append("scheme name is %r, expected %r" % (scheme.get("name"), SCHEME_NAME))
        meta = scheme.find("metaInfo")
        if meta is not None and any(p.get("name") == "originalScheme" for p in meta):
            errors.append('scheme has an "originalScheme" property')
        attributes = [o.get("name") for o in scheme.find("attributes")]
        unknown = [k for k in attributes if k not in known]
        if unknown:
            errors.append("unknown attributes keys (IntelliJ ignores them): %s" % ", ".join(unknown))
        duplicated = sorted({k for k in attributes if attributes.count(k) > 1})
        if duplicated:
            errors.append("keys defined twice: %s" % ", ".join(duplicated))

    if errors:
        print("INVALID %s" % jar_path)
        for e in errors:
            print("  - " + e)
        sys.exit(1)
    print("OK %s (version %s, scheme %s, %d keys)" % (jar_path, version, SCHEME_NAME, len(attributes)))


if __name__ == "__main__":
    main()
