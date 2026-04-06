import React from "react";
import { Key, Plus, Copy, Check, Trash2, Clock, AlertCircle, FileText, ExternalLink, ShieldCheck, Brain } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";

export function AccessSettings({
    promptsKeys,
    memoryKeys,
    loadingPrompts,
    loadingMemory,
    createPromptKeyDialog,
    setCreatePromptKeyDialog,
    createMemoryKeyDialog,
    setCreateMemoryKeyDialog,
    deletePromptKeyDialog,
    setDeletePromptKeyDialog,
    deleteMemoryKeyDialog,
    setDeleteMemoryKeyDialog,
    selectedKey,
    setSelectedKey,
    newKeyName,
    setNewKeyName,
    newMemoryKey,
    setNewMemoryKey,
    createdKey,
    setCreatedKey,
    copied,
    onCopyKey,
    onCreatePromptKey,
    onDeletePromptKey,
    onCreateMemoryKey,
    onDeleteMemoryKey,
    onToggleMemoryKey,
    creating,
    formatDate
}) {
    return (
        <div className="space-y-8 max-w-5xl">

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {/* Prompts Keys Section */}
                <section className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <h3 className="text-lg font-semibold flex items-center gap-2">
                                <ShieldCheck className="w-5 h-5 text-blue-500" />
                                Prompts Keys
                            </h3>
                            <p className="text-sm text-muted-foreground">For external apps to render your prompts</p>
                        </div>
                        <Button size="sm" onClick={() => setCreatePromptKeyDialog(true)}>
                            <Plus className="w-4 h-4 mr-1" /> New Key
                        </Button>
                    </div>

                    <div className="space-y-3">
                        {promptsKeys.length === 0 ? (
                            <Card className="border-dashed bg-transparent">
                                <CardContent className="py-8 text-center text-muted-foreground text-sm">
                                    No Prompts Keys found.
                                </CardContent>
                            </Card>
                        ) : (
                            promptsKeys.map((key) => (
                                <div key={key.id} className="flex items-center justify-between p-3 border rounded-lg bg-card">
                                    <div className="min-w-0">
                                        <p className="font-medium truncate">{key.name}</p>
                                        <code className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded mr-2">
                                            {key.key_preview}
                                        </code>
                                        <span className="text-[10px] text-muted-foreground">
                                            {key.last_used ? `Used ${formatDate(key.last_used)}` : "Never used"}
                                        </span>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="text-destructive h-8 w-8"
                                        onClick={() => {
                                            setSelectedKey(key);
                                            setDeletePromptKeyDialog(true);
                                        }}
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </Button>
                                </div>
                            ))
                        )}
                    </div>
                </section>

                {/* Memory Keys Section */}
                <section className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <h3 className="text-lg font-semibold flex items-center gap-2">
                                <Brain className="w-5 h-5 text-purple-500" />
                                Memory Keys
                            </h3>
                            <p className="text-sm text-muted-foreground">For external agents to push memories</p>
                        </div>
                        <Button size="sm" onClick={() => setCreateMemoryKeyDialog(true)}>
                            <Plus className="w-4 h-4 mr-1" /> New Key
                        </Button>
                    </div>

                    <div className="space-y-3">
                        {memoryKeys.length === 0 ? (
                            <Card className="border-dashed bg-transparent">
                                <CardContent className="py-8 text-center text-muted-foreground text-sm">
                                    No Memory Keys found.
                                </CardContent>
                            </Card>
                        ) : (
                            memoryKeys.map((agent) => (
                                <div key={agent.id} className="flex items-center justify-between p-3 border rounded-lg bg-card">
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2">
                                            <p className="font-medium truncate">{agent.name}</p>
                                            <Badge variant="outline" className="text-[10px] h-4">{agent.access_level}</Badge>
                                        </div>
                                        <code className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded mr-2">
                                            {agent.api_key_preview || agent.key_preview}
                                        </code>
                                        <span className="text-[10px] text-muted-foreground">
                                            {agent.last_used ? `Used ${formatDate(agent.last_used)}` : "Never used"}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <Switch
                                            checked={agent.is_active}
                                            onCheckedChange={() => onToggleMemoryKey(agent)}
                                            className="scale-75"
                                        />
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="text-destructive h-8 w-8"
                                            onClick={() => {
                                                setSelectedKey(agent);
                                                setDeleteMemoryKeyDialog(true);
                                            }}
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </Button>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </section>
            </div>

            {/* API Documentation Section */}
            <Card className="border-primary/20 bg-primary/5">
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-primary/10">
                            <FileText className="w-5 h-5 text-primary" />
                        </div>
                        <div>
                            <CardTitle>API Documentation</CardTitle>
                            <CardDescription>
                                View the interactive OpenAPI (Swagger) documentation to explore and test the available endpoints.
                            </CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="flex gap-4">
                        <Button asChild variant="default" className="font-mono">
                            <a href="/api/docs" target="_blank" rel="noopener noreferrer">
                                <ExternalLink className="w-4 h-4 mr-2" />
                                Swagger UI
                            </a>
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Create Prompt Key Dialog */}
            <Dialog open={createPromptKeyDialog} onOpenChange={(v) => { if (!v) { setCreatedKey(null); setNewKeyName(""); } setCreatePromptKeyDialog(v); }}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>{createdKey ? "Key Created" : "Create Prompts Key"}</DialogTitle>
                        <DialogDescription>
                            {createdKey ? "Copy this key now. It won't be shown again." : "Name this key to identify its usage (e.g. 'Landing Page Widget')"}
                        </DialogDescription>
                    </DialogHeader>
                    {createdKey ? (
                        <div className="space-y-4 py-2">
                            <div className="flex gap-2">
                                <Input value={createdKey.key} readOnly className="font-mono bg-muted" />
                                <Button onClick={() => onCopyKey(createdKey.key)} variant="outline">
                                    {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                                </Button>
                            </div>
                            <Alert variant="warning" className="bg-amber-500/10 border-amber-500/20 text-amber-500">
                                <AlertCircle className="w-4 h-4" />
                                <AlertDescription>You will not be able to retrieve this key again once closed.</AlertDescription>
                            </Alert>
                        </div>
                    ) : (
                        <div className="space-y-4 py-2">
                            <div className="space-y-2">
                                <Label>Key Name</Label>
                                <Input
                                    value={newKeyName}
                                    onChange={(e) => setNewKeyName(e.target.value)}
                                    placeholder="e.g. My Website Widget"
                                />
                            </div>
                        </div>
                    )}
                    <DialogFooter>
                        {createdKey ? (
                            <Button onClick={() => { setCreatePromptKeyDialog(false); setCreatedKey(null); }}>Done</Button>
                        ) : (
                            <>
                                <Button variant="ghost" onClick={() => setCreatePromptKeyDialog(false)}>Cancel</Button>
                                <Button onClick={onCreatePromptKey} disabled={creating || !newKeyName.trim()}>
                                    {creating ? "Creating..." : "Create Key"}
                                </Button>
                            </>
                        )}
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Create Memory Key Dialog */}
            <Dialog open={createMemoryKeyDialog} onOpenChange={(v) => { if (!v) { setCreatedKey(null); setNewMemoryKey({ name: "", description: "", access_level: "private" }); } setCreateMemoryKeyDialog(v); }}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>{createdKey ? "Key Created" : "Create Memory Key"}</DialogTitle>
                        <DialogDescription>
                            {createdKey ? "Copy this key now. It won't be shown again." : "Configure a key for an external agent."}
                        </DialogDescription>
                    </DialogHeader>
                    {createdKey ? (
                        <div className="space-y-4 py-2">
                            <div className="flex gap-2">
                                <Input value={createdKey.api_key} readOnly className="font-mono bg-muted" />
                                <Button onClick={() => onCopyKey(createdKey.api_key)} variant="outline">
                                    {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                                </Button>
                            </div>
                            <Alert variant="warning" className="bg-amber-500/10 border-amber-500/20 text-amber-500">
                                <AlertCircle className="w-4 h-4" />
                                <AlertDescription>You will not be able to retrieve this key again once closed.</AlertDescription>
                            </Alert>
                        </div>
                    ) : (
                        <div className="space-y-4 py-2">
                            <div className="space-y-2">
                                <Label>Agent Name</Label>
                                <Input
                                    value={newMemoryKey.name}
                                    onChange={(e) => setNewMemoryKey({ ...newMemoryKey, name: e.target.value })}
                                    placeholder="e.g. Slack Bot"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Description</Label>
                                <Input
                                    value={newMemoryKey.description}
                                    onChange={(e) => setNewMemoryKey({ ...newMemoryKey, description: e.target.value })}
                                    placeholder="What does this agent do?"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Access Level</Label>
                                <Select
                                    value={newMemoryKey.access_level}
                                    onValueChange={(v) => setNewMemoryKey({ ...newMemoryKey, access_level: v })}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="private">Private (read/write own data)</SelectItem>
                                        <SelectItem value="shared">Shared (read/write shared data)</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                    )}
                    <DialogFooter>
                        {createdKey ? (
                            <Button onClick={() => { setCreateMemoryKeyDialog(false); setCreatedKey(null); }}>Done</Button>
                        ) : (
                            <>
                                <Button variant="ghost" onClick={() => setCreateMemoryKeyDialog(false)}>Cancel</Button>
                                <Button onClick={onCreateMemoryKey} disabled={creating || !newMemoryKey.name.trim()}>
                                    {creating ? "Creating..." : "Create Key"}
                                </Button>
                            </>
                        )}
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Delete Prompt Key Confirmation */}
            <AlertDialog open={deletePromptKeyDialog} onOpenChange={setDeletePromptKeyDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Prompts Key</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete "{selectedKey?.name}"? External apps using this key will lose access immediately.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={onDeletePromptKey} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                            Delete Key
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            {/* Delete Memory Key Confirmation */}
            <AlertDialog open={deleteMemoryKeyDialog} onOpenChange={setDeleteMemoryKeyDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Memory Key</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete "{selectedKey?.name}"? The agent using this key will no longer be able to push memories.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={onDeleteMemoryKey} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                            Delete Key
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
