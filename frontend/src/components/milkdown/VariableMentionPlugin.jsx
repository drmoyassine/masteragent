import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Plugin, PluginKey } from '@milkdown/kit/prose/state';
import { $prose } from '@milkdown/kit/utils';
import { Building, FileText } from 'lucide-react';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

// ---------------------------------------------------------------------------
// Module-level singleton state
// This is intentional: ProseMirror plugins run outside of React's lifecycle,
// so we use a plain object + listener pattern to bridge to React.
// The singleton is safe because there is only ever one active editor at a time
// (section switching causes a full remount via key={section.filename}).
// ---------------------------------------------------------------------------
const mentionState = {
  active: false,
  triggerPos: 0,  // position in ProseMirror doc AFTER the '@' character
  query: "",      // text typed after '@', used to filter the popover list
  coords: { top: 0, left: 0 },
  view: null,
  listeners: new Set(),
  notify() {
    this.listeners.forEach(l => l({ ...this }));
  },
  reset() {
    this.active = false;
    this.triggerPos = 0;
    this.query = "";
    this.view = null;
    this.notify();
  }
};

const mentionPluginKey = new PluginKey('variableMention');

// ---------------------------------------------------------------------------
// ProseMirror Plugin
// ---------------------------------------------------------------------------
const createMentionPlugin = () => {
  return new Plugin({
    key: mentionPluginKey,

    props: {
      handleKeyDown(_view, event) {
        if (!mentionState.active) return false;
        if (event.key === 'Escape') {
          mentionState.reset();
          return true; // consume event so ProseMirror doesn't handle it
        }
        return false;
      },

      handleTextInput(view, from, _to, text) {
        if (text !== '@') return false;

        // Only trigger when '@' is at start of document or preceded by whitespace.
        // We read the character before the insertion point from the current doc.
        const prevChar = from > 0 ? view.state.doc.textBetween(from - 1, from) : ' ';
        if (!/[\s\n]/.test(prevChar) && from !== 0) return false;

        // Defer until after ProseMirror has committed the '@' insertion.
        requestAnimationFrame(() => {
          const { state } = view;
          // selection.from now points to the position right after the '@'
          const posAfterAt = state.selection.from;
          const coords = view.coordsAtPos(posAfterAt);

          mentionState.active = true;
          mentionState.triggerPos = posAfterAt; // cursor is right after '@'
          mentionState.query = "";
          mentionState.coords = { top: coords.top, left: coords.left };
          mentionState.view = view;
          mentionState.notify();
        });

        return false; // let ProseMirror insert the '@' normally
      },
    },

    // The view() lifecycle tracks cursor movements after '@' is typed.
    view() {
      return {
        update(view) {
          if (!mentionState.active) return;

          const { state } = view;
          const cursorPos = state.selection.from;

          // If cursor moved before the trigger point, close the popover.
          if (cursorPos < mentionState.triggerPos) {
            mentionState.reset();
            return;
          }

          // Guard: don't read past document end.
          if (cursorPos > state.doc.content.size) {
            mentionState.reset();
            return;
          }

          // Read the text between trigger and cursor. If a space/newline was
          // typed, the mention is cancelled.
          const textSinceTrigger = state.doc.textBetween(mentionState.triggerPos, cursorPos);
          if (textSinceTrigger.includes(' ') || textSinceTrigger.includes('\n')) {
            mentionState.reset();
            return;
          }

          // Update the query string and recompute popover coordinates.
          mentionState.query = textSinceTrigger;
          const coords = view.coordsAtPos(mentionState.triggerPos);
          mentionState.coords = { top: coords.top, left: coords.left };
          mentionState.notify();
        },

        destroy() {
          // Clean up when this editor instance is destroyed (e.g., section switch).
          mentionState.reset();
        },
      };
    },
  });
};

// ---------------------------------------------------------------------------
// React popover — subscribes to mentionState changes
// ---------------------------------------------------------------------------
export function MentionPopover({ variablesRef }) {
  const [state, setState] = useState({
    active: false,
    query: "",
    coords: { top: 0, left: 0 },
    view: null,
    triggerPos: 0,
  });

  // Subscribe to the singleton state.
  useEffect(() => {
    const listener = (snapshot) => setState(snapshot);
    mentionState.listeners.add(listener);
    return () => mentionState.listeners.delete(listener);
  }, []);

  const { active, query, coords, view, triggerPos } = state;

  // Handle variable selection from the command menu.
  const handleSelect = useCallback((variableName) => {
    if (!view) return;

    const { state: editorState, dispatch } = view;

    // Replace from the '@' char (triggerPos - 1) through to the current cursor,
    // which includes the '@' + whatever query text was typed so far.
    const from = Math.max(0, triggerPos - 1); // position of '@'
    const to = editorState.selection.from;     // current cursor (end of query text)

    const tr = editorState.tr.insertText(`{{${variableName}}}`, from, to);
    dispatch(tr);
    view.focus();

    mentionState.reset();
  }, [view, triggerPos]);

  if (!active) return null;

  const variables = variablesRef.current || [];
  const promptVariables = variables.filter(v => v.source === "prompt");
  const accountVariables = variables.filter(v => v.source === "account");

  // Filter both lists by the current query
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
    >
      <Command
        className="w-64 rounded-md border shadow-md bg-popover text-popover-foreground"
        shouldFilter={false}
      >
        {/*
          IMPORTANT: CommandInput here is a DISPLAY-ONLY search field.
          Its value is driven by `query` (the text already typed in the editor
          after '@'). We do NOT dispatch any ProseMirror transactions from
          onValueChange — the actual query text lives in the ProseMirror doc,
          not in this input. The input is read-only and just mirrors the query.
        */}
        <CommandInput
          placeholder="Search variables..."
          value={query}
          readOnly
          className="h-8"
        />
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

// Milkdown plugin export — wraps our ProseMirror plugin into Milkdown's system.
export const variableMentionPlugin = $prose(() => createMentionPlugin());
