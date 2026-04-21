import React, { useEffect, useRef, useImperativeHandle, forwardRef, memo } from 'react';
import { Milkdown, MilkdownProvider, useEditor } from '@milkdown/react';
import { Editor, rootCtx, defaultValueCtx } from '@milkdown/kit/core';
import { commonmark } from '@milkdown/kit/preset/commonmark';
import { listener, listenerCtx } from '@milkdown/kit/plugin/listener';
import { insert } from '@milkdown/kit/utils';
import { variableMentionPlugin, MentionPopover } from './milkdown/VariableMentionPlugin';

const MilkdownInner = forwardRef(({ value, onChange, variables }, ref) => {
  const variablesRef = useRef(variables);

  // Keep the variables ref current so the plugin always reads the latest list
  // without triggering an editor rebuild.
  useEffect(() => {
    variablesRef.current = variables;
  }, [variables]);

  // useEditor returns { loading, get } — NOT { editor, get }.
  // `get()` returns the Editor instance (or undefined while loading).
  const { get } = useEditor((root) => {
    return Editor.make()
      .config((ctx) => {
        ctx.set(rootCtx, root);
        ctx.set(defaultValueCtx, value || '');

        // NOTE: the callback receives (_ctx, markdown, prevMarkdown).
        // We name the first arg `_ctx` to avoid shadowing the outer `ctx`.
        ctx.get(listenerCtx).markdownUpdated((_ctx, markdown, prevMarkdown) => {
          if (onChange && markdown !== prevMarkdown) {
            onChange(markdown);
          }
        });
      })
      .use(commonmark)
      .use(listener)
      .use(variableMentionPlugin);
  }, []); // Empty deps: editor must never remount on prop changes.
           // Section switching is handled by key={section.filename} in the parent.

  // Expose an imperative insertText() to the parent via forwarded ref.
  // We call get() at call time rather than caching the instance in a ref,
  // which avoids the bug where editorRef.current is null if get() resolves async.
  useImperativeHandle(ref, () => ({
    insertText: (text) => {
      const editorInstance = get();
      if (editorInstance) {
        // insert(text, true) inserts as inline text at the current cursor.
        editorInstance.action(insert(text, true));
      }
    }
  }));

  return (
    <>
      {/*
        <Milkdown> does not accept className — it renders a bare div.
        We wrap it in a div that carries the styling class instead.
      */}
      <div className="milkdown-editor prose prose-invert max-w-none">
        <Milkdown />
      </div>
      <MentionPopover variablesRef={variablesRef} />
    </>
  );
});

MilkdownInner.displayName = 'MilkdownInner';

// The outer component wraps everything in MilkdownProvider.
// Section switching is handled by key={section.filename} in PromptEditorPage,
// which forces a full React remount — cleanly resetting ProseMirror state.
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
