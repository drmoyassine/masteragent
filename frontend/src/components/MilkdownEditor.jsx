import React, { useEffect, useRef, useImperativeHandle, forwardRef, memo } from 'react';
import { Milkdown, MilkdownProvider, useEditor } from '@milkdown/react';
import { Editor, rootCtx, defaultValueCtx, editorViewCtx } from '@milkdown/kit/core';
import { commonmark } from '@milkdown/kit/preset/commonmark';
import { listener, listenerCtx } from '@milkdown/kit/plugin/listener';
import { insert } from '@milkdown/kit/utils';
import { attachMentionDetection, MentionPopover } from './milkdown/VariableMentionPlugin';
import { SlashMenu } from './milkdown/SlashMenu';

import { slashFactory } from '@milkdown/kit/plugin/slash';

const MilkdownInner = forwardRef(({ value, onChange, variables }, ref) => {
  const variablesRef = useRef(variables);
  const cleanupRef = useRef(null);

  // Keep variables ref current without triggering editor rebuilds.
  useEffect(() => {
    variablesRef.current = variables;
  }, [variables]);

  // useEditor returns { loading, get }.
  // get() returns the Editor instance (or undefined while loading).
  const { get, loading } = useEditor((root) => {
    return Editor.make()
      .config((ctx) => {
        ctx.set(rootCtx, root);
        ctx.set(defaultValueCtx, value || '');

        ctx.get(listenerCtx).markdownUpdated((_ctx, markdown, prevMarkdown) => {
          if (onChange && markdown !== prevMarkdown) {
            onChange(markdown);
          }
        });
      })
      .use(commonmark)
      .use(listener)
      .use(slashFactory('my-slash'));
  }, []); // Empty deps: key={section.filename} handles section switching.

  // After the editor finishes loading, grab the ProseMirror EditorView
  // and attach our mention detection DOM listeners.
  useEffect(() => {
    if (loading) return;

    const editorInstance = get();
    if (!editorInstance) return;

    // Use editor.action() to safely access the ProseMirror EditorView via ctx
    try {
      editorInstance.action((ctx) => {
        const view = ctx.get(editorViewCtx);
        if (view && view.dom) {
          // Attach DOM-based mention detection
          cleanupRef.current = attachMentionDetection(view);
        }
      });
    } catch (e) {
      console.warn('[MilkdownEditor] Could not attach mention detection:', e);
    }

    return () => {
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
    };
  }, [loading, get]);

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
      <MentionPopover variablesRef={variablesRef} />
      <SlashMenu />
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
