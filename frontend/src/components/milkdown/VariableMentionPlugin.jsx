import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Building, FileText } from 'lucide-react';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

// ---------------------------------------------------------------------------
// Module-level mention state
// Bridges imperative DOM events → React rendering via a listener pattern.
// Safe as a singleton because only one editor exists at a time
// (section switching causes full remount via key={section.filename}).
// ---------------------------------------------------------------------------
const mentionState = {
  active: false,
  triggerPos: 0,  // ProseMirror doc position right AFTER the '@'
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

/**
 * Attach mention detection to a ProseMirror EditorView via DOM events.
 * Returns a cleanup function.
 */
export function attachMentionDetection(view) {
  if (!view || !view.dom) return () => {};

  // After every DOM input event, check if we should activate / update / close
  const handleInput = () => {
    const { state } = view;
    const { from } = state.selection;

    if (!mentionState.active) {
      // Check if user just typed '@' — look at the character before cursor
      if (from < 1) return;
      const charBeforeCursor = state.doc.textBetween(from - 1, from);
      if (charBeforeCursor !== '@') return;

      // Check that '@' is preceded by whitespace or is at start of text block
      const twoBack = from >= 2 ? state.doc.textBetween(from - 2, from - 1) : ' ';
      if (!/[\s\n]/.test(twoBack) && from - 1 !== state.selection.$from.start()) return;

      // Activate!
      const coords = view.coordsAtPos(from);
      mentionState.active = true;
      mentionState.triggerPos = from; // position right after '@'
      mentionState.query = "";
      mentionState.coords = { top: coords.top, left: coords.left };
      mentionState.view = view;
      mentionState.notify();
      return;
    }

    // Already active — update the query or close
    const cursorPos = from;

    if (cursorPos < mentionState.triggerPos) {
      mentionState.reset();
      return;
    }

    if (cursorPos > state.doc.content.size) {
      mentionState.reset();
      return;
    }

    const textSinceTrigger = state.doc.textBetween(mentionState.triggerPos, cursorPos);

    if (textSinceTrigger.includes(' ') || textSinceTrigger.includes('\n')) {
      mentionState.reset();
      return;
    }

    mentionState.query = textSinceTrigger;
    const coords = view.coordsAtPos(mentionState.triggerPos);
    mentionState.coords = { top: coords.top, left: coords.left };
    mentionState.notify();
  };

  const handleKeyDown = (e) => {
    if (!mentionState.active) return;
    if (e.key === 'Escape') {
      mentionState.reset();
      e.preventDefault();
      e.stopPropagation();
    }
  };

  // Listen on the ProseMirror contenteditable element
  view.dom.addEventListener('input', handleInput);
  view.dom.addEventListener('keydown', handleKeyDown, true);

  return () => {
    view.dom.removeEventListener('input', handleInput);
    view.dom.removeEventListener('keydown', handleKeyDown, true);
    mentionState.reset();
  };
}

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
    // Replace from '@' (triggerPos - 1) through current cursor with {{variable}}
    const from = Math.max(0, triggerPos - 1);
    const to = editorState.selection.from;

    const tr = editorState.tr.insertText(`{{${variableName}}}`, from, to);
    dispatch(tr);
    view.focus();
    mentionState.reset();
  }, [view, triggerPos]);

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
    >
      <Command
        className="w-64 rounded-md border shadow-md bg-popover text-popover-foreground"
        shouldFilter={false}
      >
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
