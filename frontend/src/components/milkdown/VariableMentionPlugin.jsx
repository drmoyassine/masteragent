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

// Trigger characters that activate the variable autocomplete
const TRIGGER_CHARS = ['@'];

// ---------------------------------------------------------------------------
// Module-level mention state
// Bridges imperative DOM events → React rendering via a listener pattern.
// ---------------------------------------------------------------------------
const mentionState = {
  active: false,
  triggerPos: 0,
  triggerChar: '',
  query: "",
  coords: { top: 0, left: 0 },
  view: null,
  listeners: new Set(),
  notify() {
    this.listeners.forEach(l => l({
      active: this.active,
      triggerPos: this.triggerPos,
      triggerChar: this.triggerChar,
      query: this.query,
      coords: { ...this.coords },
      view: this.view,
    }));
  },
  reset() {
    this.active = false;
    this.triggerPos = 0;
    this.triggerChar = '';
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

  const checkMention = () => {
    const { state } = view;
    const { from } = state.selection;

    if (!mentionState.active) {
      // --- ACTIVATION: check if the char before cursor is a trigger ---
      if (from < 1) return;

      const charBeforeCursor = state.doc.textBetween(from - 1, from);
      if (!TRIGGER_CHARS.includes(charBeforeCursor)) return;

      // Ensure the trigger is at start of text block or preceded by whitespace
      const resolvedPos = state.selection.$from;
      const startOfTextBlock = resolvedPos.start();
      const triggerOffset = from - 1;

      if (triggerOffset > startOfTextBlock) {
        const charBeforeTrigger = state.doc.textBetween(triggerOffset - 1, triggerOffset);
        if (!/[\s\n]/.test(charBeforeTrigger)) return;
      }

      // Activate
      const coords = view.coordsAtPos(from);
      mentionState.active = true;
      mentionState.triggerPos = from; // position right after trigger char
      mentionState.triggerChar = charBeforeCursor;
      mentionState.query = "";
      mentionState.coords = { top: coords.top, left: coords.left };
      mentionState.view = view;
      mentionState.notify();
      return;
    }

    // --- ALREADY ACTIVE: update query or close ---
    const cursorPos = from;

    if (cursorPos < mentionState.triggerPos) {
      mentionState.reset();
      return;
    }

    if (cursorPos > state.doc.content.size) {
      mentionState.reset();
      return;
    }

    const textSinceTrigger = cursorPos > mentionState.triggerPos
      ? state.doc.textBetween(mentionState.triggerPos, cursorPos)
      : "";

    if (textSinceTrigger.includes(' ') || textSinceTrigger.includes('\n')) {
      mentionState.reset();
      return;
    }

    mentionState.query = textSinceTrigger;
    const coords = view.coordsAtPos(mentionState.triggerPos);
    mentionState.coords = { top: coords.top, left: coords.left };
    mentionState.notify();
  };

  // Use requestAnimationFrame to ensure ProseMirror has finished processing
  // the keystroke and updated view.state before we read from it.
  // Without this, the input event fires before ProseMirror settles,
  // causing us to read stale positions → flash/disappear bug.
  const handleInput = () => {
    requestAnimationFrame(checkMention);
  };

  const handleKeyDown = (e) => {
    if (!mentionState.active) return;
    if (e.key === 'Escape') {
      mentionState.reset();
      e.preventDefault();
      e.stopPropagation();
    }
  };

  // Also close the popover when clicking outside
  const handleClickOutside = (e) => {
    if (!mentionState.active) return;
    // If click is outside the editor, close
    if (!view.dom.contains(e.target)) {
      mentionState.reset();
    }
  };

  view.dom.addEventListener('input', handleInput);
  view.dom.addEventListener('keydown', handleKeyDown, true);
  document.addEventListener('mousedown', handleClickOutside);

  return () => {
    view.dom.removeEventListener('input', handleInput);
    view.dom.removeEventListener('keydown', handleKeyDown, true);
    document.removeEventListener('mousedown', handleClickOutside);
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
    triggerChar: '',
  });

  useEffect(() => {
    const listener = (snapshot) => setState(snapshot);
    mentionState.listeners.add(listener);
    return () => mentionState.listeners.delete(listener);
  }, []);

  const { active, query, coords, view, triggerPos, triggerChar } = state;

  const handleSelect = useCallback((variableName) => {
    if (!view) return;

    const { state: editorState, dispatch } = view;
    // Replace from trigger char position through current cursor with {{variable}}
    const from = Math.max(0, triggerPos - 1); // include the trigger char itself
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

  const triggerLabel = triggerChar === '/' ? 'slash' : '@';

  return createPortal(
    <div
      className="fixed z-50 animate-in fade-in zoom-in-95"
      style={{ top: coords.top + 22, left: coords.left }}
      onMouseDown={(e) => e.preventDefault()} // prevent editor blur
    >
      <Command
        className="w-64 rounded-md border shadow-md bg-popover text-popover-foreground"
        shouldFilter={false}
      >
        <div className="px-3 py-1.5 text-xs text-muted-foreground border-b">
          Insert variable via <code className="text-xs">{triggerLabel}</code>
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
