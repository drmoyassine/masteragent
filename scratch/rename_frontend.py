import os
import re

path = 'frontend/src/components/settings/MemorySettings.jsx'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

intelligence_tab = """
// ─── Intelligence Tab ───────────────────────────────────────────────────
function IntelligenceTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline }) {
    const privatePipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === \\"intelligence\\").sort((a,b) => a.execution_order - b.execution_order);

    return (
        <div className=\\"space-y-6\\">
            <div className=\\"mb-2\\">
                <h3 className=\\"text-lg font-semibold flex items-center gap-2\\">
                    <Brain className=\\"w-5 h-5 text-purple-500\\" />
                    Intelligence Pipeline
                </h3>
                <p className=\\"text-sm text-muted-foreground mt-1\\">
                    Extracts high-level intelligence and semantic insights from memory records.
                </p>
            </div>

            {/* Intelligence Pipeline Assignment */}
            <Card className=\\"border-dashed bg-muted/20\\">
                <CardHeader className=\\"pb-3 border-b\\">
                    <CardTitle className=\\"text-sm\\">Intelligence Pipeline</CardTitle>
                </CardHeader>
                <CardContent className=\\"pt-4\\">
                    <DraggablePipeline 
                        title=\\"\\"
                        pipelineStage=\\"intelligence\\"
                        pipelineConfigs={privatePipelineNodes}
                        onReorder={(arr) => onReorderPipeline(\\"intelligence\\", arr)}
                        llmProviders={llmProviders}
                        onSaveConfig={onSaveConfig} onDeleteConfig={onDeleteConfig}
                        onAddConfig={onAddConfig}
                        modelLists={modelLists}
                        fetchingModels={fetchingModels}
                        fetchErrors={fetchErrors}
                        onFetchModels={onFetchModels}
                    />
                </CardContent>
            </Card>
        </div>
    );
}

"""

knowledge_tab = """
// ─── Knowledge Tab ──────────────────────────────────────────────────────
function KnowledgeTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline }) {
    const publicPipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === \\"knowledge\\").sort((a,b) => a.execution_order - b.execution_order);

    return (
        <div className=\\"space-y-6\\">
            <div className=\\"mb-2\\">
                <h3 className=\\"text-lg font-semibold flex items-center gap-2\\">
                    <GraduationCap className=\\"w-5 h-5 text-indigo-500\\" />
                    Knowledge Generation
                </h3>
                <p className=\\"text-sm text-muted-foreground mt-1\\">
                    Generates agnostic, PII-scrubbed, reusable Knowledge items.
                </p>
            </div>

            {/* PII Privacy */}
            <Card>
                <CardHeader className=\\"pb-3\\">
                    <div className=\\"flex items-center gap-2\\">
                        <ShieldAlert className=\\"w-5 h-5 text-red-500\\" />
                        <CardTitle className=\\"text-lg\\">PII Privacy</CardTitle>
                    </div>
                    <CardDescription className=\\"text-xs\\">
                        Configure PII scrubbing layer for knowledge sharing.
                    </CardDescription>
                </CardHeader>
                <CardContent className=\\"space-y-4\\">
                    <div className=\\"flex items-center justify-between\\">
                        <div className=\\"space-y-0.5\\">
                            <Label>Enable PII Scrubbing</Label>
                            <p className=\\"text-[10px] text-muted-foreground\\">
                                Automatically strip PII from shared data
                            </p>
                        </div>
                        <Switch
                            checked={settings.pii_scrubbing_enabled}
                            onCheckedChange={(v) => onUpdateSettings(\\"pii_scrubbing_enabled\\", v)}
                        />
                    </div>
                    <div className=\\"flex items-center justify-between\\">
                        <div className=\\"space-y-0.5\\">
                            <Label>Auto-share Scrubbed</Label>
                            <p className=\\"text-[10px] text-muted-foreground\\">
                                Automatically share PII-stripped memories
                            </p>
                        </div>
                        <Switch
                            checked={settings.auto_share_scrubbed}
                            onCheckedChange={(v) => onUpdateSettings(\\"auto_share_scrubbed\\", v)}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Knowledge Mining */}
            <Card>
                <CardHeader className=\\"pb-3\\">
                    <div className=\\"flex items-center gap-2\\">
                        <GraduationCap className=\\"w-5 h-5 text-green-500\\" />
                        <CardTitle className=\\"text-lg\\">Knowledge Mining</CardTitle>
                    </div>
                    <CardDescription className=\\"text-xs\\">
                        Automatic knowledge generation from accumulated confirmed intelligence items
                    </CardDescription>
                </CardHeader>
                <CardContent className=\\"space-y-4\\">
                    <div className=\\"flex items-center justify-between\\">
                        <div className=\\"space-y-0.5\\">
                            <Label>Auto-extract Knowledge</Label>
                            <p className=\\"text-[10px] text-muted-foreground\\">
                                Automatically mine knowledge from intelligence
                            </p>
                        </div>
                        <Switch
                            checked={settings.auto_knowledge_enabled}
                            onCheckedChange={(v) => onUpdateSettings(\\"auto_knowledge_enabled\\", v)}
                        />
                    </div>
                    <div className=\\"space-y-2\\">
                        <Label className=\\"text-xs font-mono\\">
                            Knowledge Threshold (N intelligence items)
                        </Label>
                        <Input
                            type=\\"number\\"
                            min={2}
                            value={settings.knowledge_threshold || 5}
                            onChange={(e) =>
                                onUpdateSettings(\\"knowledge_threshold\\", parseInt(e.target.value))
                            }
                            disabled={!settings.auto_knowledge_enabled}
                        />
                        <p className=\\"text-[10px] text-muted-foreground\\">
                            Generate a knowledge item after this many confirmed intelligence items accumulate.
                        </p>
                    </div>
                    <div className=\\"space-y-2\\">
                        <Label className=\\"text-xs font-mono\\">
                            Knowledge Trigger (days, optional)
                        </Label>
                        <Input
                            type=\\"number\\"
                            min={1}
                            placeholder=\\"Leave blank to use count only\\"
                            value={settings.knowledge_trigger_days || \\"\\"}
                            onChange={(e) => {
                                const v = e.target.value;
                                onUpdateSettings(\\"knowledge_trigger_days\\", v ? parseInt(v) : null);
                            }}
                            disabled={!settings.auto_knowledge_enabled}
                        />
                        <p className=\\"text-[10px] text-muted-foreground\\">
                            Also trigger if oldest unused intelligence is this many days old (min 2).
                        </p>
                    </div>
                </CardContent>
            </Card>

            {/* Knowledge Pipeline Assignment */}
            <Card className=\\"border-dashed bg-muted/20\\">
                <CardHeader className=\\"pb-3 border-b\\">
                    <CardTitle className=\\"text-sm\\">Knowledge Pipeline</CardTitle>
                </CardHeader>
                <CardContent className=\\"pt-4\\">
                    <DraggablePipeline 
                        title=\\"\\"
                        pipelineStage=\\"knowledge\\"
                        pipelineConfigs={publicPipelineNodes}
                        onReorder={(arr) => onReorderPipeline(\\"knowledge\\", arr)}
                        llmProviders={llmProviders}
                        onSaveConfig={onSaveConfig} onDeleteConfig={onDeleteConfig}
                        onAddConfig={onAddConfig}
                        modelLists={modelLists}
                        fetchingModels={fetchingModels}
                        fetchErrors={fetchErrors}
                        onFetchModels={onFetchModels}
                    />
                </CardContent>
            </Card>

            {/* Queue Dynamics */}
            <Card>
                <CardHeader className=\\"pb-3\\">
                    <div className=\\"flex items-center gap-2\\">
                        <Cpu className=\\"w-5 h-5 text-indigo-500\\" />
                        <CardTitle className=\\"text-lg\\">Queue Dynamics</CardTitle>
                    </div>
                    <CardDescription className=\\"text-xs mt-1.5\\">
                        Parallel BullMQ execution workers for knowledge generation.
                    </CardDescription>
                </CardHeader>
                <CardContent className=\\"space-y-4\\">
                    <div className=\\"space-y-2\\">
                        <Label className=\\"text-xs font-mono\\">Max Concurrency</Label>
                        <Input
                            type=\\"number\\"
                            min=\\"1\\"
                            max=\\"50\\"
                            value={settings.knowledge_queue_concurrency || 1}
                            onChange={(e) =>
                                onUpdateSettings(
                                    \\"knowledge_queue_concurrency\\",
                                    parseInt(e.target.value) || 1
                                )
                            }
                        />
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
"""

# Find boundaries
match = re.search(r'//\s*───\s*Knowledgeration Tab.*?(?=//\s*───\s*Analytics Tab)', text, re.DOTALL | re.IGNORECASE)
if match:
    text = text[:match.start()] + intelligence_tab + "\\n" + knowledge_tab + "\\n" + text[match.end():]
else:
    print("Warning: Could not find Knowledgeration Tab")

text = text.replace(
'''<TabsTrigger value="knowledge_generation" className="flex items-center gap-2">
                        <GraduationCap className="w-4 h-4" />
                        <span className="hidden sm:inline">Knowledge</span>
                    </TabsTrigger>''',
'''<TabsTrigger value="intelligence" className="flex items-center gap-2">
                        <Brain className="w-4 h-4" />
                        <span className="hidden sm:inline">Intelligence</span>
                    </TabsTrigger>
                    <TabsTrigger value="knowledge" className="flex items-center gap-2">
                        <GraduationCap className="w-4 h-4" />
                        <span className="hidden sm:inline">Knowledge</span>
                    </TabsTrigger>'''
)

text = text.replace(
'''<TabsContent value="knowledge_generation">
                    <KnowledgeGenerationTab {...tabProps} />
                </TabsContent>''',
'''<TabsContent value="intelligence">
                    <IntelligenceTab {...tabProps} />
                </TabsContent>

                <TabsContent value="knowledge">
                    <KnowledgeTab {...tabProps} />
                </TabsContent>'''
)

# Fix backslashes introduced by string escaping issues previously
text = text.replace('\\"', '"')

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print('MemorySettings.jsx updated successfully!')
