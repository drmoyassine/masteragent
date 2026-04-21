import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Building, FileText } from 'lucide-react';
import { $prose } from '@milkdown/kit/utils';
import { Plugin, PluginKey } from '@milkdown/prose/state';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

// ---------------------------------------------------------------------------
// Module-level mention state — bridges ProseMirror plugin → React rendering
// ---------------------------------------------------------------------------
const mentionState = {
  active: false,
  triggerPos: 0, // doc position right AFTER the '@'
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
// ProseMirror plugin — detects '@' in view.update (fires AFTER state settles)
// ---------------------------------------------------------------------------
export const mentionPlugin = $prose(() => {
  return new Plugin({
    key: new PluginKey('variable-mention'),
    view() {
      // Reset when a new editor mounts (section switch via key={})
      mentionState.reset();

      return {
        update(view, prevState) {
          const { state } = view;

          // Skip if neither doc nor selection changed
          if (prevState.doc.eq(state.doc) && prevState.selection.eq(state.selection)) return;

          const { from } = state.selection;

          if (!mentionState.active) {
            // Only activate on actual text changes, not cursor-only moves
            if (prevState.doc.eq(state.doc)) return;
            if (from < 1) return;

            const charBefore = state.doc.textBetween(from - 1, from);
            if (charBefore !== '@') return;

            // Ensure trigger is at start of text block or preceded by whitespace
            const $from = state.selection.$from;
            const startOfBlock = $from.start();
            const triggerOffset = from - 1;

            if (triggerOffset > startOfBlock) {
              const charBeforeTrigger = state.doc.textBetween(triggerOffset - 1, triggerOffset);
              if (!/[\s\n]/.test(charBeforeTrigger)) return;
            }

            // Activate
            const coords = view.coordsAtPos(from);
            mentionState.active = true;
            mentionState.triggerPos = from;
            mentionState.query = "";
            mentionState.coords = { top: coords.top, left: coords.left };
            mentionState.view = view;
            mentionState.notify();
            return;
          }

          // --- ACTIVE: update query or close ---
          if (from < mentionState.triggerPos) {
            mentionState.reset();
            return;
          }

          // Verify '@' is still at the trigger position
          if (mentionState.triggerPos < 1 || mentionState.triggerPos - 1 >= state.doc.content.size) {
            mentionState.reset();
            return;
          }
          const triggerChar = state.doc.textBetween(mentionState.triggerPos - 1, mentionState.triggerPos);
          if (triggerChar !== '@') {
            mentionState.reset();
            return;
          }

          const textSinceTrigger = from > mentionState.triggerPos
            ? state.doc.textBetween(mentionState.triggerPos, from)
            : "";

          if (textSinceTrigger.includes(' ') || textSinceTrigger.includes('\n')) {
            mentionState.reset();
            return;
          }

          mentionState.query = textSinceTrigger;
          const coords = view.coordsAtPos(mentionState.triggerPos);
          mentionState.coords = { top: coords.top, left: coords.left };
          mentionState.notify();
        },

        destroy() {
          mentionState.reset();
        },
      };
    },
  });
});

// ---------------------------------------------------------------------------
// React popover — subscribes to mentionState
// ---------------------------------------------------------------------------
export function MentionPopover({ variablesRef }) {
  const [state, setState] = useState({
    active: false,
    query: "",
    coords: { top: 0, left: 0 },
    view: null,
    triggerPos: 0,
  });

  useEffect(() => {
    const listener = (snapshot) => setState(snapshot);
    mentionState.listeners.add(listener);
    return () => mentionState.listeners.delete(listener);
  }, []);

  const { active, query, coords, view, triggerPos } = state;

  const handleSelect = useCallback((variableName) => {
    if (!view) return;

    const { state: editorState, dispatch } = view;
    // Replace from '@' (triggerPos - 1) through cursor with {{variable}}
    const from = Math.max(0, triggerPos - 1);
    const to = editorState.selection.from;
    const tr = editorState.tr.insertText(`{{${variableName}}}`, from, to);
    dispatch(tr);
    view.focus();
    mentionState.reset();
  }, [view, triggerPos]);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!mentionState.active) return;
      if (e.key === 'Escape') {
        mentionState.reset();
        e.preventDefault();
        e.stopPropagation();
      }
    };
    document.addEventListener('keydown', handleKeyDown, true);
    return () => document.removeEventListener('keydown', handleKeyDown, true);
  }, []);

  if (!active) return null;

  const variables = variablesRef.current || [];
  const promptVariables = variables.filter(v => v.source === "prompt");
  const accountVariables = variables.filter(v => v.source === "account");

  const filteredPrompt = promptVariables.filter(v =>
    v.name.toLowerCase().includes(query.toLowerCase())
  );
  const filteredAccount = accountVariables.filter(v =>
    v.name.toLowerCase().includes(query.toLowerCase())
  );

  return createPortal(
    <div
      className="fixed z-50 animate-in fade-in zoom-in-95"
      style={{ top: coords.top + 22, left: coords.left }}
      onMouseDown={(e) => e.preventDefault()}
    >
      <Command
        className="w-64 rounded-md border shadow-md bg-popover text-popover-foreground"
        shouldFilter={false}
      >
        <div className="px-3 py-1.5 text-xs text-muted-foreground border-b">
          Insert variable via <code className="text-xs">@</code>
          {query && <span> · filtering: <code className="text-xs">{query}</code></span>}
        </div>
        <CommandList className="max-h-64 overflow-y-auto">
          <CommandEmpty>No variables found.</CommandEmpty>

          {filteredPrompt.length > 0 && (
            <CommandGroup heading="Prompt Variables">
              {filteredPrompt.map(v => (
                <CommandItem
                  key={`prompt-${v.name}`}
                  value={v.name}
                  onSelect={() => handleSelect(v.name)}
                >
                  <FileText className="w-3 h-3 mr-2 text-muted-foreground" />
                  <code className="text-sm font-mono">{v.name}</code>
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          {filteredPrompt.length > 0 && filteredAccount.length > 0 && (
            <CommandSeparator />
          )}

          {filteredAccount.length > 0 && (
            <CommandGroup heading="Account Variables">
              {filteredAccount.map(v => (
                <CommandItem
                  key={`account-${v.name}`}
                  value={v.name}
                  onSelect={() => handleSelect(v.name)}
                >
                  <Building className="w-3 h-3 mr-2 text-muted-foreground" />
                  <code className="text-sm font-mono">{v.name}</code>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </Command>
    </div>,
    document.body
  );
}
