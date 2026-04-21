import React, { useEffect, useRef, useCallback } from 'react';
import { useInstance } from '@milkdown/react';
import { editorViewCtx, commandsCtx } from '@milkdown/kit/core';
import { SlashProvider } from '@milkdown/kit/plugin/slash';
import { callCommand } from '@milkdown/kit/utils';
import {
  createCodeBlockCommand,
  insertHrCommand,
  turnIntoTextCommand,
  wrapInBlockquoteCommand,
  wrapInBulletListCommand,
  wrapInHeadingCommand,
  wrapInOrderedListCommand,
} from '@milkdown/kit/preset/commonmark';
import {
  Heading1, Heading2, Heading3,
  List, ListOrdered, Quote, Code, Minus, Type,
} from 'lucide-react';

// Menu configuration — each item maps to a Milkdown command
const SLASH_ITEMS = [
  { label: 'Text',           icon: Type,        command: turnIntoTextCommand.key },
  { label: 'Heading 1',      icon: Heading1,    command: wrapInHeadingCommand.key, args: 1 },
  { label: 'Heading 2',      icon: Heading2,    command: wrapInHeadingCommand.key, args: 2 },
  { label: 'Heading 3',      icon: Heading3,    command: wrapInHeadingCommand.key, args: 3 },
  { label: 'Bullet List',    icon: List,        command: wrapInBulletListCommand.key },
  { label: 'Ordered List',   icon: ListOrdered, command: wrapInOrderedListCommand.key },
  { label: 'Blockquote',     icon: Quote,       command: wrapInBlockquoteCommand.key },
  { label: 'Code Block',     icon: Code,        command: createCodeBlockCommand.key },
  { label: 'Divider',        icon: Minus,       command: insertHrCommand.key },
];

/**
 * Slash menu component — renders inside the editor and is positioned by SlashProvider.
 * Uses Milkdown's official plugin-slash architecture.
 */
export function SlashMenu() {
  const menuRef = useRef(null);
  const providerRef = useRef(null);
  const [loading, getEditor] = useInstance();
  const [selectedIndex, setSelectedIndex] = React.useState(0);

  // Execute a slash command
  const executeCommand = useCallback((item) => {
    if (loading) return;
    const editor = getEditor();
    if (!editor) return;

    editor.action((ctx) => {
      // First clear the '/' trigger text from the current block
      const view = ctx.get(editorViewCtx);
      const { state } = view;
      const { $from } = state.selection;

      // Find the '/' character and delete it + any query text after it
      const parentText = $from.parent.textContent;
      const slashIndex = parentText.lastIndexOf('/');
      if (slashIndex >= 0) {
        const startOfParent = $from.start();
        const from = startOfParent + slashIndex;
        const to = $from.pos;
        const tr = state.tr.delete(from, to);
        view.dispatch(tr);
      }

      // Then execute the actual command
      const commands = ctx.get(commandsCtx);
      commands.call(item.command, item.args);
    });

    providerRef.current?.hide();
  }, [loading, getEditor]);

  // Set up SlashProvider after editor loads
  useEffect(() => {
    if (loading || !menuRef.current) return;

    const editor = getEditor();
    if (!editor) return;

    // Create the slash provider using Milkdown's official API
    const provider = new SlashProvider({
      content: menuRef.current,
      trigger: '/',
      debounce: 50,
      offset: 8,
    });

    providerRef.current = provider;

    // Hook the provider into the editor's update cycle
    // by accessing the ProseMirror view
    editor.action((ctx) => {
      const view = ctx.get(editorViewCtx);

      // SlashProvider.update() needs to be called on every editor view update.
      // We wrap it into ProseMirror's plugin view lifecycle via a direct subscription.
      const originalDispatch = view.dispatch.bind(view);
      view.dispatch = (...args) => {
        const prevState = view.state;
        originalDispatch(...args);
        provider.update(view, prevState);
      };

      // Also handle initial state
      provider.update(view);
    });

    return () => {
      provider.destroy();
      providerRef.current = null;
    };
  }, [loading, getEditor]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!menuRef.current || menuRef.current.dataset.show !== 'true') return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(i => (i + 1) % SLASH_ITEMS.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(i => (i - 1 + SLASH_ITEMS.length) % SLASH_ITEMS.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        executeCommand(SLASH_ITEMS[selectedIndex]);
        setSelectedIndex(0);
      } else if (e.key === 'Escape') {
        providerRef.current?.hide();
        setSelectedIndex(0);
      }
    };

    document.addEventListener('keydown', handleKeyDown, true);
    return () => document.removeEventListener('keydown', handleKeyDown, true);
  }, [selectedIndex, executeCommand]);

  return (
    <div
      ref={menuRef}
      className="hidden data-[show=true]:block absolute z-50 w-56 rounded-md border shadow-md bg-popover text-popover-foreground p-1 animate-in fade-in zoom-in-95"
    >
      <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground border-b mb-1">
        Block Type
      </div>
      {SLASH_ITEMS.map((item, idx) => {
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
              e.preventDefault(); // prevent editor blur
              executeCommand(item);
              setSelectedIndex(0);
            }}
          >
            <Icon className="w-4 h-4 text-muted-foreground" />
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
