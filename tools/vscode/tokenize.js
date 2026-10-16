// Tokenize a Java file exactly the way VS Code's TextMate layer does, and resolve
// each token's foreground/fontStyle against a VS Code color theme.
// Usage: node tokenize.js <grammar.json> <theme.json> <source.java> <out.json>
const fs = require('fs');
const path = require('path');
const vsctm = require('vscode-textmate');
const oniguruma = require('vscode-oniguruma');

const [grammarPath, themePath, sourcePath, outPath] = process.argv.slice(2);

// VS Code theme files are JSONC (comments, trailing commas)
function readJsonc(p) {
  const text = fs.readFileSync(p, 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/,(\s*[\]}])/g, '$1');
  return JSON.parse(text);
}

const theme = readJsonc(themePath);
const editorFg = theme.colors['editor.foreground'];
const editorBg = theme.colors['editor.background'];

// Same rule list VS Code hands to vscode-textmate (ColorThemeData.tokenColors):
// the unscoped default rule first, then every theme rule that has scope + settings.
const settings = [{ settings: { foreground: editorFg, background: editorBg } }];
for (const r of theme.tokenColors) {
  if (r.scope && r.settings) {
    settings.push({ scope: r.scope, settings: { foreground: r.settings.foreground, background: r.settings.background, fontStyle: r.settings.fontStyle } });
  }
}

const wasm = fs.readFileSync(path.join(path.dirname(require.resolve('vscode-oniguruma')), 'onig.wasm')).buffer;
const onigLib = oniguruma.loadWASM(wasm).then(() => ({
  createOnigScanner: (patterns) => new oniguruma.OnigScanner(patterns),
  createOnigString: (s) => new oniguruma.OnigString(s),
}));

const registry = new vsctm.Registry({
  onigLib,
  loadGrammar: async (scopeName) => {
    if (scopeName === 'source.java') {
      return vsctm.parseRawGrammar(fs.readFileSync(grammarPath, 'utf8'), grammarPath);
    }
    return null;
  },
});
registry.setTheme({ name: theme.name, settings });

(async () => {
  const grammar = await registry.loadGrammar('source.java');
  const colorMap = registry.getColorMap();
  const lines = fs.readFileSync(sourcePath, 'utf8').split('\n');
  let ruleStack = vsctm.INITIAL;
  const out = [];
  lines.forEach((line, lineNo) => {
    const scoped = grammar.tokenizeLine(line, ruleStack);
    const binary = grammar.tokenizeLine2(line, ruleStack);
    ruleStack = scoped.ruleStack;
    // binary tokens: pairs [startIndex, metadata]
    const styles = [];
    for (let i = 0; i < binary.tokens.length; i += 2) {
      const start = binary.tokens[i];
      const end = i + 2 < binary.tokens.length ? binary.tokens[i + 2] : line.length;
      const meta = binary.tokens[i + 1];
      const fontStyle = (meta & 0x00007800) >>> 11;
      const fg = (meta & 0x00ff8000) >>> 15;
      styles.push({ start, end, fg: colorMap[fg].toUpperCase(), italic: !!(fontStyle & 1), bold: !!(fontStyle & 2), underline: !!(fontStyle & 4), strikethrough: !!(fontStyle & 8) });
    }
    const tokens = scoped.tokens.map((t) => ({ start: t.startIndex, end: Math.min(t.endIndex, line.length), scopes: t.scopes }));
    out.push({ line: lineNo, text: line, tokens, styles });
  });
  fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
  console.log('lines:', out.length);
})();
