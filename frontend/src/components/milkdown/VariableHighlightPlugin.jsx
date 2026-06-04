import { $prose } from '@milkdown/kit/utils';
import { Plugin, PluginKey } from '@milkdown/prose/state';
import { Decoration, DecorationSet } from '@milkdown/prose/view';

// Matches {{ variable.name }} tokens — mirrors the backend extract_variables
// regex (services/prompt_renderer.py) so the editor highlights exactly what
// the renderer will treat as a variable.
const VARIABLE_RE = /\{\{\s*[a-zA-Z_][a-zA-Z0-9_.]*\s*\}\}/g;

function buildDecorations(doc) {
  const decorations = [];
  doc.descendants((node, pos) => {
    if (!node.isText || !node.text) return;
    const text = node.text;
    VARIABLE_RE.lastIndex = 0;
    let match;
    while ((match = VARIABLE_RE.exec(text)) !== null) {
      const start = pos + match.index;
      const end = start + match[0].length;
      decorations.push(
        Decoration.inline(start, end, { class: 'milkdown-variable-pill' })
      );
    }
  });
  return DecorationSet.create(doc, decorations);
}

// ProseMirror plugin that decorates {{ variables }} as green pills. Decorations
// are render-only — they never alter the document or the saved markdown.
export const variableHighlightPlugin = $prose(() => {
  return new Plugin({
    key: new PluginKey('variable-highlight'),
    props: {
      decorations(state) {
        return buildDecorations(state.doc);
      },
    },
  });
});
