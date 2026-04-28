import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Bold, Italic, Code, Strikethrough, Braces, Link } from 'lucide-react';
import { $prose } from '@milkdown/kit/utils';
import { Plugin, PluginKey } from '@milkdown/prose/state';
import { toggleMark } from '@milkdown/prose/commands';

// ---------------------------------------------------------------------------
// Module-level selection state — bridges ProseMirror → React
// ---------------------------------------------------------------------------
const selectionState = {
  active: false,
  coords: { top: 0, left: 0 },
  view: null,
  listeners: new Set(),
  notify() {
    this.listeners.forEach(l => l({
      active: this.active,
      coords: { ...this.coords },
      view: this.view,
    }));
  },
  reset() {
    this.active = false;
    this.view = null;
    this.notify();
  },
};

// ---------------------------------------------------------------------------
// ProseMirror plugin — detects non-empty text selections
// ---------------------------------------------------------------------------
export const selectionToolbarPlugin = $prose(() => {
  return new Plugin({
    key: new PluginKey('selection-toolbar'),
    view() {
      selectionState.reset();

      return {
        update(view) {
          const { state } = view;
          const { from, to, empty } = state.selection;

          // Only show on non-empty text selections (not node selections)
          if (empty || from === to) {
            if (selectionState.active) selectionState.reset();
            return;
          }

          // Get coords at the middle of the selection for centering
          const start = view.coordsAtPos(from);
          const end = view.coordsAtPos(to);
          const left = (start.left + end.left) / 2;
          const top = Math.min(start.top, end.top);

          selectionState.active = true;
          selectionState.coords = { top, left };
          selectionState.view = view;
          selectionState.notify();
        },

        destroy() {
          selectionState.reset();
        },
      };
    },
  });
});

// ---------------------------------------------------------------------------
// Toolbar button definitions
// ---------------------------------------------------------------------------
const TOOLBAR_BUTTONS = [
  { key: 'bold', icon: Bold, title: 'Bold', markType: 'strong' },
  { key: 'italic', icon: Italic, title: 'Italic', markType: 'emphasis' },
  { key: 'code', icon: Code, title: 'Inline Code', markType: 'inlineCode' },
  { key: 'strikethrough', icon: Strikethrough, title: 'Strikethrough', markType: 'strikethrough' },
  { key: 'variable', icon: Braces, title: 'Wrap as Variable', action: 'wrapVariable' },
];

// ---------------------------------------------------------------------------
// React toolbar — subscribes to selectionState
// ---------------------------------------------------------------------------
export function SelectionToolbar() {
  const [state, setState] = useState({
    active: false,
    coords: { top: 0, left: 0 },
    view: null,
  });

  useEffect(() => {
    const listener = (snapshot) => setState(snapshot);
    selectionState.listeners.add(listener);
    return () => selectionState.listeners.delete(listener);
  }, []);

  const { active, coords, view } = state;

  const handleAction = useCallback((button) => {
    if (!view) return;

    if (button.action === 'wrapVariable') {
      // Wrap selected text in {{ }}
      const { state: editorState, dispatch } = view;
      const { from, to } = editorState.selection;
      const selectedText = editorState.doc.textBetween(from, to);
      const tr = editorState.tr.replaceWith(
        from, to,
        editorState.schema.text(`{{${selectedText}}}`)
      );
      dispatch(tr);
      view.focus();
      selectionState.reset();
      return;
    }

    if (button.markType) {
      const { state: editorState } = view;
      const markType = editorState.schema.marks[button.markType];
      if (!markType) return;

      toggleMark(markType)(editorState, view.dispatch);
      view.focus();
      return;
    }
  }, [view]);

  // Hide on click outside
  useEffect(() => {
    if (!active) return;
    const handleMouseDown = (e) => {
      const toolbar = document.getElementById('selection-toolbar');
      if (toolbar && !toolbar.contains(e.target)) {
        // Don't reset here — let the ProseMirror plugin handle it
      }
    };
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [active]);

  if (!active) return null;

  return createPortal(
    <div
      id="selection-toolbar"
      className="fixed z-50 animate-in fade-in zoom-in-95 duration-100"
      style={{
        top: coords.top - 44,
        left: coords.left,
        transform: 'translateX(-50%)',
      }}
      onMouseDown={(e) => e.preventDefault()}
    >
      <div className="flex items-center gap-0.5 px-1.5 py-1 rounded-lg border border-border/60 bg-popover shadow-lg backdrop-blur-sm">
        {TOOLBAR_BUTTONS.map((button, index) => {
          const Icon = button.icon;
          return (
            <React.Fragment key={button.key}>
              {index === TOOLBAR_BUTTONS.length - 1 && (
                <div className="w-px h-5 bg-border/50 mx-0.5" />
              )}
              <button
                onClick={() => handleAction(button)}
                title={button.title}
                className="p-1.5 rounded-md hover:bg-muted/70 transition-colors text-muted-foreground hover:text-foreground"
              >
                <Icon className="w-3.5 h-3.5" />
              </button>
            </React.Fragment>
          );
        })}
      </div>
    </div>,
    document.body
  );
}
