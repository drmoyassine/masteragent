import React, { useEffect, useRef, useImperativeHandle, forwardRef, memo } from 'react';
import { Milkdown, MilkdownProvider, useEditor } from '@milkdown/react';
import { Editor, rootCtx, defaultValueCtx } from '@milkdown/kit/core';
import { commonmark } from '@milkdown/kit/preset/commonmark';
import { gfm } from '@milkdown/kit/preset/gfm';
import { listener, listenerCtx } from '@milkdown/kit/plugin/listener';
import { insert } from '@milkdown/kit/utils';
import { tableBlock, tableBlockConfig } from '@milkdown/kit/component/table-block';
import { mentionPlugin, MentionPopover } from './milkdown/VariableMentionPlugin';
import { slashPlugin, SlashMenu } from './milkdown/SlashMenu';
import { selectionToolbarPlugin, SelectionToolbar } from './milkdown/SelectionToolbar';

// SVG icons for table controls (small, monochrome, 16x16)
const icons = {
  add_row:         '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
  add_col:         '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
  delete_row:      '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  delete_col:      '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  align_col_left:  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg>',
  align_col_center:'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="10" x2="6" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="18" y1="18" x2="6" y2="18"/></svg>',
  align_col_right: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="21" y1="10" x2="7" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="7" y2="18"/></svg>',
  col_drag_handle: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="5" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="19" r="1"/></svg>',
  row_drag_handle: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="5" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="19" r="1"/></svg>',
};

const MilkdownInner = forwardRef(({ value, onChange, variables, onCreateVariable }, ref) => {
  const variablesRef = useRef(variables);

  // Keep variables ref current without triggering editor rebuilds.
  useEffect(() => {
    variablesRef.current = variables;
  }, [variables]);

  // useEditor returns { loading, get }.
  const { get } = useEditor((root) => {
    return Editor.make()
      .config((ctx) => {
        ctx.set(rootCtx, root);
        ctx.set(defaultValueCtx, value || '');

        // Configure table block icons
        ctx.update(tableBlockConfig.key, (prev) => ({
          ...prev,
          renderButton: (type) => icons[type] ?? prev.renderButton(type),
        }));

        ctx.get(listenerCtx).markdownUpdated((_ctx, markdown, prevMarkdown) => {
          if (onChange && markdown !== prevMarkdown) {
            onChange(markdown);
          }
        });
      })
      .use(commonmark)
      .use(gfm)
      .use(tableBlock)
      .use(listener)
      .use(mentionPlugin)
      .use(slashPlugin)
      .use(selectionToolbarPlugin);
  }, []); // Empty deps: key={section.filename} handles section switching.

  // Expose imperative insertText() to the parent via ref.
  useImperativeHandle(ref, () => ({
    insertText: (text) => {
      const editorInstance = get();
      if (editorInstance) {
        editorInstance.action(insert(text, true));
      }
    }
  }));

  return (
    <>
      <div className="milkdown-editor prose prose-invert max-w-none">
        <Milkdown />
      </div>
      <MentionPopover variablesRef={variablesRef} onCreateVariable={onCreateVariable} />
      <SlashMenu />
      <SelectionToolbar />
    </>
  );
});

MilkdownInner.displayName = 'MilkdownInner';

const MilkdownEditor = forwardRef((props, ref) => {
  const { 'data-testid': testId, ...rest } = props;
  return (
    <div className="w-full h-full relative" data-testid={testId}>
      <MilkdownProvider>
        <MilkdownInner {...rest} ref={ref} />
      </MilkdownProvider>
    </div>
  );
});

MilkdownEditor.displayName = 'MilkdownEditor';

export default memo(MilkdownEditor);
