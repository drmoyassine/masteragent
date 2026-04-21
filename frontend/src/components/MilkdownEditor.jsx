import React, { useEffect, useRef, useImperativeHandle, forwardRef, memo } from 'react';
import { Milkdown, MilkdownProvider, useEditor } from '@milkdown/react';
import { Editor, rootCtx, defaultValueCtx } from '@milkdown/kit/core';
import { commonmark } from '@milkdown/kit/preset/commonmark';
import { gfm } from '@milkdown/kit/preset/gfm';
import { listener, listenerCtx } from '@milkdown/kit/plugin/listener';
import { insert } from '@milkdown/kit/utils';
import { mentionPlugin, MentionPopover } from './milkdown/VariableMentionPlugin';
import { slashPlugin, SlashMenu } from './milkdown/SlashMenu';

const MilkdownInner = forwardRef(({ value, onChange, variables }, ref) => {
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

        ctx.get(listenerCtx).markdownUpdated((_ctx, markdown, prevMarkdown) => {
          if (onChange && markdown !== prevMarkdown) {
            onChange(markdown);
          }
        });
      })
      .use(commonmark)
      .use(gfm)
      .use(listener)
      .use(mentionPlugin)
      .use(slashPlugin);
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
