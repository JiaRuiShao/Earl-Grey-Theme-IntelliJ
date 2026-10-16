#!/usr/bin/env bash
# Builds the Earl Grey UI Theme plugin (Marketplace id wtf.halt.earlgrey.theme):
#   build/EarlGreyTheme-<version>.jar
# Layout matches the published 1.1.0 jar: /earlgrey.theme.json, /EarlGrey.xml and the node icons at the jar root,
# so existing installs keep their paths. The editor scheme is generated from "Earl Grey.icls" and keeps the
# published scheme name "EarlGrey" (renaming it would leave users with an orphaned copy of the old name).
# Usage: tools/build-plugin.sh [version]   (default 1.2.0). Needs Python 3 and a JDK for the `jar` tool.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-1.2.0}"
STAGE="$ROOT/build/plugin"
OUT="$ROOT/build/EarlGreyTheme-$VERSION.jar"

rm -rf "$STAGE" && mkdir -p "$STAGE/META-INF"
sed "s/@VERSION@/$VERSION/g" "$ROOT/plugin/META-INF/plugin.xml" > "$STAGE/META-INF/plugin.xml"
cp "$ROOT/plugin/META-INF/pluginIcon.svg" "$STAGE/META-INF/pluginIcon.svg"
cp "$ROOT/plugin/theme/earlgrey.theme.json" "$STAGE/"
cp "$ROOT/plugin/theme/icons/"*.svg "$STAGE/"
# Parity License "Notices": every copy carries the license text with its contributor and source code lines
cp "$ROOT/LICENSE-PARITY.md" "$ROOT/LICENSE-APACHE.txt" "$STAGE/META-INF/"

python3 - "$ROOT/Earl Grey.icls" "$STAGE/EarlGrey.xml" <<'EOF'
import sys
import xml.etree.ElementTree as ET

src, out = sys.argv[1], sys.argv[2]
tree = ET.parse(src)
root = tree.getroot()
NAME = "EarlGrey"  # the name published in 1.0/1.1: users' selected scheme is stored under it
root.set("name", NAME)
meta = root.find("metaInfo")
for prop in meta.findall("property"):
    if prop.get("name") == "originalScheme":
        prop.text = NAME  # must be the scheme's own name: the _@user_ copy takes its display name from it
desc = ET.SubElement(meta, "property", {"name": "description"})
desc.text = ("A gentle, low-contrast light theme, following the design principles of Earl Grey "
             "(https://earl-grey.halt.wtf/).")
# keep the 1.1.0 line spacing so existing users see no layout change
spacing = ET.Element("option", {"name": "LINE_SPACING", "value": "1.25"})
root.insert(list(root).index(meta) + 1, spacing)
ET.indent(tree, space="  ")
tree.write(out, encoding="UTF-8", xml_declaration=False)
EOF

rm -f "$OUT"
jar --create --file "$OUT" -C "$STAGE" .
echo "$OUT"
