import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useInstance } from '@milkdown/react';
import { editorViewCtx, commandsCtx } from '@milkdown/kit/core';
import { $prose } from '@milkdown/kit/utils';
import { Plugin, PluginKey } from '@milkdown/prose/state';
import {
  createCodeBlockCommand,
  insertHrCommand,
  turnIntoTextCommand,
  wrapInBlockquoteCommand,
  wrapInBulletListCommand,
  wrapInHeadingCommand,
  wrapInOrderedListCommand,
} from '@milkdown/kit/preset/commonmark';
import { insertTableCommand } from '@milkdown/kit/preset/gfm';
import {
  Heading1, Heading2, Heading3,
  List, ListOrdered, Quote, Code, Minus, Type, Table,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Slash menu item definitions
// ---------------------------------------------------------------------------
const SLASH_ITEMS = [
  { label: 'Text',           icon: Type,        commandKey: turnIntoTextCommand.key },
  { label: 'Heading 1',      icon: Heading1,    commandKey: wrapInHeadingCommand.key, args: 1 },
  { label: 'Heading 2',      icon: Heading2,    commandKey: wrapInHeadingCommand.key, args: 2 },
  { label: 'Heading 3',      icon: Heading3,    commandKey: wrapInHeadingCommand.key, args: 3 },
  { label: 'Bullet List',    icon: List,        commandKey: wrapInBulletListCommand.key },
  { label: 'Ordered List',   icon: ListOrdered, commandKey: wrapInOrderedListCommand.key },
  { label: 'Table',          icon: Table,       commandKey: insertTableCommand.key, args: { row: 3, col: 3 } },
  { label: 'Blockquote',     icon: Quote,       commandKey: wrapInBlockquoteCommand.key },
  { label: 'Code Block',     icon: Code,        commandKey: createCodeBlockCommand.key },
  { label: 'Divider',        icon: Minus,       commandKey: insertHrCommand.key },
];

// ---------------------------------------------------------------------------
// Module-level slash state — bridges ProseMirror plugin → React rendering
// ---------------------------------------------------------------------------
const slashState = {
  active: false,
  triggerPos: 0, // doc position right AFTER the '/'
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
            // Only activate on text changes
            if (prevState.doc.eq(state.doc)) return;
            if (from < 1) return;

            const charBefore = state.doc.textBetween(from - 1, from);
            if (charBefore !== '/') return;

            // Must be at start of text block or preceded by whitespace
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

          // --- ACTIVE: update query or close ---
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
// React popover — subscribes to slashState
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
      setSelectedIndex(0); // reset selection on any state change
    };
    slashState.listeners.add(listener);
    return () => slashState.listeners.delete(listener);
  }, []);

  const { active, query, coords, view, triggerPos } = state;

  // Filter items by query
  const filteredItems = SLASH_ITEMS.filter(item =>
    item.label.toLowerCase().includes(query.toLowerCase())
  );

  // Execute: Step 1 — delete '/' + query, Step 2 — run command
  const executeCommand = useCallback((item) => {
    if (loading || !view) return;
    const editor = getEditor();
    if (!editor) return;

    // Step 1: Delete the '/' trigger and any query text
    const { state: editorState } = view;
    const deleteFrom = Math.max(0, triggerPos - 1); // include the '/'
    const deleteTo = editorState.selection.from;
    if (deleteFrom < deleteTo) {
      view.dispatch(editorState.tr.delete(deleteFrom, deleteTo));
    }

    // Step 2: Execute the block command on the now-updated state
    try {
      editor.action((ctx) => {
        const commands = ctx.get(commandsCtx);
        commands.call(item.commandKey, item.args);
      });
    } catch (e) {
      console.warn('[SlashMenu] Command failed:', item.label, e);
    }

    view.focus();
    slashState.reset();
  }, [loading, getEditor, view, triggerPos]);

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
