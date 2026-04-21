import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useInstance } from '@milkdown/react';
import { editorViewCtx } from '@milkdown/kit/core';
import { $prose } from '@milkdown/kit/utils';
import { Plugin, PluginKey } from '@milkdown/prose/state';
import { setBlockType, wrapIn } from '@milkdown/prose/commands';
import {
  Heading1, Heading2, Heading3,
  List, ListOrdered, Quote, Code, Minus, Type, Table,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Command executors — bypass Milkdown's CommandManager, use ProseMirror directly
// ---------------------------------------------------------------------------
function executeSetBlockType(view, nodeTypeName, attrs) {
  const nodeType = view.state.schema.nodes[nodeTypeName];
  if (!nodeType) {
    console.warn(`[SlashMenu] Node type "${nodeTypeName}" not found in schema`);
    return false;
  }
  return setBlockType(nodeType, attrs)(view.state, view.dispatch, view);
}

function executeWrapIn(view, nodeTypeName) {
  const nodeType = view.state.schema.nodes[nodeTypeName];
  if (!nodeType) {
    console.warn(`[SlashMenu] Node type "${nodeTypeName}" not found in schema`);
    return false;
  }
  return wrapIn(nodeType)(view.state, view.dispatch, view);
}

function executeInsertTable(view, rows = 3, cols = 3) {
  const { schema } = view.state;
  const tableType = schema.nodes.table;
  const tableHeaderRowType = schema.nodes.table_header_row;
  const tableRowType = schema.nodes.table_row;
  const tableHeaderCellType = schema.nodes.table_header;
  const tableCellType = schema.nodes.table_cell;
  const paragraphType = schema.nodes.paragraph;

  if (!tableType || !tableHeaderRowType || !tableRowType || !paragraphType) {
    console.warn('[SlashMenu] Table node types not found in schema. Available:', Object.keys(schema.nodes));
    return false;
  }

  // Build header cells (th) — must use table_header node type + alignment attr
  const headerCells = Array.from({ length: cols }, () =>
    tableHeaderCellType.createAndFill({ alignment: 'left' })
  );
  const headerRow = tableHeaderRowType.create(null, headerCells);

  // Build data rows with table_cell node type
  const dataRows = Array.from({ length: Math.max(rows - 1, 1) }, () => {
    const cells = Array.from({ length: cols }, () =>
      tableCellType.createAndFill({ alignment: 'left' })
    );
    return tableRowType.create(null, cells);
  });

  const table = tableType.create(null, [headerRow, ...dataRows]);

  const { tr, selection } = view.state;
  const _tr = tr.replaceSelectionWith(table);

  // Place cursor in the first header cell
  const resolvedPos = _tr.doc.resolve(selection.from + 3);
  const sel = view.state.constructor.near
    ? view.state.constructor.near(resolvedPos)
    : null;

  view.dispatch(_tr.scrollIntoView());
  return true;
}

function executeInsertHr(view) {
  const hrType = view.state.schema.nodes.hr;
  if (!hrType) {
    console.warn('[SlashMenu] HR node type not found in schema');
    return false;
  }
  const { tr, selection } = view.state;
  view.dispatch(tr.replaceSelectionWith(hrType.create()).scrollIntoView());
  return true;
}

// ---------------------------------------------------------------------------
// Slash menu item definitions — each has a direct executor
// ---------------------------------------------------------------------------
const SLASH_ITEMS = [
  { label: 'Text',           icon: Type,        exec: (v) => executeSetBlockType(v, 'paragraph') },
  { label: 'Heading 1',      icon: Heading1,    exec: (v) => executeSetBlockType(v, 'heading', { level: 1 }) },
  { label: 'Heading 2',      icon: Heading2,    exec: (v) => executeSetBlockType(v, 'heading', { level: 2 }) },
  { label: 'Heading 3',      icon: Heading3,    exec: (v) => executeSetBlockType(v, 'heading', { level: 3 }) },
  { label: 'Bullet List',    icon: List,        exec: (v) => executeWrapIn(v, 'bullet_list') },
  { label: 'Ordered List',   icon: ListOrdered, exec: (v) => executeWrapIn(v, 'ordered_list') },
  { label: 'Table',          icon: Table,       exec: (v) => executeInsertTable(v, 3, 3) },
  { label: 'Blockquote',     icon: Quote,       exec: (v) => executeWrapIn(v, 'blockquote') },
  { label: 'Code Block',     icon: Code,        exec: (v) => executeSetBlockType(v, 'code_block') },
  { label: 'Divider',        icon: Minus,       exec: (v) => executeInsertHr(v) },
];

// ---------------------------------------------------------------------------
// Module-level slash state
// ---------------------------------------------------------------------------
const slashState = {
  active: false,
  triggerPos: 0,
  query: "",
  coords: { top: 0, left: 0 },
  view: null,
  listeners: new Set(),
  notify() {
    this.listeners.forEach(l => l({
      active: this.active,
      triggerPos: this.triggerPos,
      query: this.query,
      coords: { ...this.coords },
      view: this.view,
    }));
  },
  reset() {
    this.active = false;
    this.triggerPos = 0;
    this.query = "";
    this.view = null;
    this.notify();
  },
};

// ---------------------------------------------------------------------------
// ProseMirror plugin — detects '/' in view.update
// ---------------------------------------------------------------------------
export const slashPlugin = $prose(() => {
  return new Plugin({
    key: new PluginKey('slash-menu'),
    view() {
      slashState.reset();

      return {
        update(view, prevState) {
          const { state } = view;

          if (prevState.doc.eq(state.doc) && prevState.selection.eq(state.selection)) return;

          const { from } = state.selection;

          if (!slashState.active) {
            if (prevState.doc.eq(state.doc)) return;
            if (from < 1) return;

            const charBefore = state.doc.textBetween(from - 1, from);
            if (charBefore !== '/') return;

            const $from = state.selection.$from;
            const startOfBlock = $from.start();
            const triggerOffset = from - 1;

            if (triggerOffset > startOfBlock) {
              const charBeforeTrigger = state.doc.textBetween(triggerOffset - 1, triggerOffset);
              if (!/[\s\n]/.test(charBeforeTrigger)) return;
            }

            const coords = view.coordsAtPos(from);
            slashState.active = true;
            slashState.triggerPos = from;
            slashState.query = "";
            slashState.coords = { top: coords.top, left: coords.left };
            slashState.view = view;
            slashState.notify();
            return;
          }

          // Update query or close
          if (from < slashState.triggerPos) {
            slashState.reset();
            return;
          }

          if (slashState.triggerPos < 1 || slashState.triggerPos - 1 >= state.doc.content.size) {
            slashState.reset();
            return;
          }
          const triggerChar = state.doc.textBetween(slashState.triggerPos - 1, slashState.triggerPos);
          if (triggerChar !== '/') {
            slashState.reset();
            return;
          }

          const textSinceTrigger = from > slashState.triggerPos
            ? state.doc.textBetween(slashState.triggerPos, from)
            : "";

          if (textSinceTrigger.includes(' ') || textSinceTrigger.includes('\n')) {
            slashState.reset();
            return;
          }

          slashState.query = textSinceTrigger;
          const coords = view.coordsAtPos(slashState.triggerPos);
          slashState.coords = { top: coords.top, left: coords.left };
          slashState.notify();
        },

        destroy() {
          slashState.reset();
        },
      };
    },
  });
});

// ---------------------------------------------------------------------------
// React popover
// ---------------------------------------------------------------------------
export function SlashMenu() {
  const [loading, getEditor] = useInstance();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [state, setState] = useState({
    active: false, query: "", coords: { top: 0, left: 0 }, view: null, triggerPos: 0,
  });

  useEffect(() => {
    const listener = (snapshot) => {
      setState(snapshot);
      setSelectedIndex(0);
    };
    slashState.listeners.add(listener);
    return () => slashState.listeners.delete(listener);
  }, []);

  const { active, query, coords, view, triggerPos } = state;

  const filteredItems = SLASH_ITEMS.filter(item =>
    item.label.toLowerCase().includes(query.toLowerCase())
  );

  // Execute: delete '/' + query, then run the ProseMirror command directly
  const executeCommand = useCallback((item) => {
    if (!view) return;

    // Step 1: Delete the '/' trigger and any query text
    const { state: editorState } = view;
    const deleteFrom = Math.max(0, triggerPos - 1);
    const deleteTo = editorState.selection.from;
    if (deleteFrom < deleteTo) {
      view.dispatch(editorState.tr.delete(deleteFrom, deleteTo));
    }

    // Step 2: Execute via direct ProseMirror commands on the updated state
    const result = item.exec(view);
    if (!result) {
      console.warn(`[SlashMenu] Command "${item.label}" returned false — may not be applicable in current context`);
    }

    view.focus();
    slashState.reset();
  }, [view, triggerPos]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!slashState.active) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        e.stopPropagation();
        setSelectedIndex(i => (i + 1) % Math.max(1, filteredItems.length));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        e.stopPropagation();
        setSelectedIndex(i => (i - 1 + filteredItems.length) % Math.max(1, filteredItems.length));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        if (filteredItems[selectedIndex]) {
          executeCommand(filteredItems[selectedIndex]);
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        slashState.reset();
      }
    };

    document.addEventListener('keydown', handleKeyDown, true);
    return () => document.removeEventListener('keydown', handleKeyDown, true);
  }, [selectedIndex, filteredItems, executeCommand]);

  if (!active || filteredItems.length === 0) return null;

  return createPortal(
    <div
      className="fixed z-50 animate-in fade-in zoom-in-95"
      style={{ top: coords.top + 22, left: coords.left }}
      onMouseDown={(e) => e.preventDefault()}
    >
      <div className="w-56 rounded-md border shadow-md bg-popover text-popover-foreground p-1">
        <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground border-b mb-1">
          Block Type
          {query && <span> · <code className="text-xs">{query}</code></span>}
        </div>
        {filteredItems.map((item, idx) => {
          const Icon = item.icon;
          return (
            <button
              key={item.label}
              className={`flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm cursor-pointer transition-colors
                ${idx === selectedIndex
                  ? 'bg-accent text-accent-foreground'
                  : 'hover:bg-accent/50 text-foreground'
                }`}
              onMouseEnter={() => setSelectedIndex(idx)}
              onMouseDown={(e) => {
                e.preventDefault();
                executeCommand(item);
              }}
            >
              <Icon className="w-4 h-4 text-muted-foreground" />
              {item.label}
            </button>
          );
        })}
      </div>
    </div>,
    document.body
  );
}
