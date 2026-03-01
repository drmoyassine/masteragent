import React from "react";
import { Github, HardDrive, ExternalLink, AlertTriangle, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

export function StorageSettings({
    settings,
    storageMode,
    formData,
    updating,
    updateDialog,
    setUpdateDialog,
    disconnectDialog,
    setDisconnectDialog,
    onModeChange,
    onUpdateSettings,
    onDisconnect,
    onFormDataChange
}) {
    return (
        <div className="max-w-2xl space-y-6">
            {/* Storage Mode Toggle */}
            <div className="border border-border rounded-sm p-6 bg-secondary/20">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-sm bg-blue-500/10 flex items-center justify-center">
                            <HardDrive className="w-5 h-5 text-blue-500" />
                        </div>
                        <div>
                            <h2 className="font-mono font-semibold text-foreground">Active Storage Mode</h2>
                            <p className="text-sm text-muted-foreground">
                                Choose where your prompts are stored
                            </p>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <Button
                        variant={storageMode === 'local' ? 'default' : 'outline'}
                        className="h-auto py-4 flex-col gap-1 font-mono"
                        onClick={() => onModeChange('local')}
                    >
                        <HardDrive className="w-5 h-5" />
                        <span className="text-xs">Local Filesystem</span>
                    </Button>
                    <Button
                        variant={storageMode === 'github' ? 'default' : 'outline'}
                        disabled={!settings?.has_github}
                        className="h-auto py-4 flex-col gap-1 font-mono"
                        onClick={() => onModeChange('github')}
                    >
                        <Github className="w-5 h-5" />
                        <span className="text-xs">GitHub Cloud</span>
                    </Button>
                </div>
                {!settings?.has_github && (
                    <p className="text-[10px] text-muted-foreground mt-2 text-center">
                        Connect GitHub below to enable cloud storage
                    </p>
                )}
            </div>

            {/* GitHub Connection */}
            <div className="border border-border rounded-sm p-6 bg-card">
                <div className="flex items-start justify-between mb-6">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-sm bg-primary/10 flex items-center justify-center">
                            <Github className="w-5 h-5 text-primary" />
                        </div>
                        <div>
                            <h2 className="font-mono font-semibold text-foreground">GitHub Connection</h2>
                            <p className="text-sm text-muted-foreground">
                                Your prompts are stored in this repository
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${settings?.has_github ? 'bg-primary animate-pulse-slow' : 'bg-muted'}`} />
                        <span className={`text-sm font-mono ${settings?.has_github ? 'text-primary' : 'text-muted-foreground'}`}>
                            {settings?.has_github ? 'Connected' : 'Not Connected'}
                        </span>
                    </div>
                </div>

                {!settings?.has_github && (
                    <div className="bg-primary/5 rounded-sm p-4 mb-6 border border-primary/10">
                        <p className="text-sm text-primary/80 mb-2">
                            Connect your GitHub account to enable cloud sync and version history for your prompts.
                        </p>
                        <div className="text-xs text-muted-foreground space-y-2">
                            <p>
                                Generate a <strong>Fine-grained Token</strong> (recommended) or <strong>Classic PAT</strong>:
                            </p>
                            <ul className="list-disc list-inside space-y-1 ml-1">
                                <li><strong>Fine-grained:</strong> Repository access &rarr; Select Repository; Permissions &rarr; <strong>Contents: Read and write</strong></li>
                                <li><strong>Classic:</strong> Enable the <code className="bg-muted px-1 rounded text-foreground">repo</code> scope</li>
                            </ul>
                            <a
                                href="https://github.com/settings/tokens?type=beta"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-primary underline inline-flex items-center"
                            >
                                Create Fine-grained Token <ExternalLink className="w-3 h-3 ml-1" />
                            </a>
                        </div>
                    </div>
                )}

                {settings?.has_github && (
                    <>
                        <div className="grid grid-cols-2 gap-4 mb-6">
                            <div className="space-y-1">
                                <span className="text-xs text-muted-foreground font-mono uppercase tracking-wider">
                                    Owner
                                </span>
                                <div className="font-mono text-foreground">{settings?.github_owner}</div>
                            </div>
                            <div className="space-y-1">
                                <span className="text-xs text-muted-foreground font-mono uppercase tracking-wider">
                                    Repository
                                </span>
                                <div className="font-mono text-foreground">{settings?.github_repo}</div>
                            </div>
                        </div>

                        <div className="flex gap-3">
                            <Button
                                variant="outline"
                                onClick={() => setUpdateDialog(true)}
                                className="font-mono"
                            >
                                Update Connection
                            </Button>
                            <Button
                                variant="outline"
                                asChild
                                className="font-mono"
                            >
                                <a
                                    href={`https://github.com/${settings?.github_owner}/${settings?.github_repo}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                >
                                    <ExternalLink className="w-4 h-4 mr-2" />
                                    View Repository
                                </a>
                            </Button>
                        </div>
                    </>
                )}

                {!settings?.has_github && (
                    <Button
                        onClick={() => setUpdateDialog(true)}
                        className="font-mono uppercase tracking-wider"
                    >
                        Connect GitHub
                    </Button>
                )}
            </div>

            {/* Danger Zone */}
            {settings?.has_github && (
                <div className="border border-destructive/30 rounded-sm p-6 bg-card">
                    <div className="flex items-center gap-3 mb-4">
                        <AlertTriangle className="w-5 h-5 text-destructive" />
                        <h2 className="font-mono font-semibold text-destructive">Danger Zone</h2>
                    </div>
                    <p className="text-sm text-muted-foreground mb-4">
                        Disconnecting will remove your GitHub configuration. Your prompts will
                        remain in the repository but won't be accessible from this instance.
                    </p>
                    <Button
                        variant="outline"
                        onClick={() => setDisconnectDialog(true)}
                        className="font-mono text-destructive border-destructive/30 hover:bg-destructive/10"
                    >
                        <Trash2 className="w-4 h-4 mr-2" />
                        Disconnect GitHub
                    </Button>
                </div>
            )}

            {/* Update Dialog */}
            <Dialog open={updateDialog} onOpenChange={setUpdateDialog}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="font-mono text-xl text-foreground">Update GitHub Connection</DialogTitle>
                        <DialogDescription className="space-y-2 pt-2">
                            <p>For cloud sync to work, your token must have:</p>
                            <ul className="text-xs list-disc list-inside opacity-80">
                                <li><strong>Fine-grained:</strong> Repository Content (Read &amp; Write)</li>
                                <li><strong>Classic PAT:</strong> full 'repo' scope</li>
                            </ul>
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="token" className="font-mono text-sm">
                                NEW TOKEN (Required)
                            </Label>
                            <Input
                                id="token"
                                type="password"
                                placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                                value={formData.github_token}
                                onChange={(e) => onFormDataChange("github_token", e.target.value)}
                                className="font-mono"
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="owner" className="font-mono text-sm">
                                    OWNER / ORG
                                </Label>
                                <Input
                                    id="owner"
                                    placeholder="username or org"
                                    value={formData.github_owner}
                                    onChange={(e) => onFormDataChange("github_owner", e.target.value)}
                                    className="font-mono"
                                />
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="repo" className="font-mono text-sm">
                                    REPOSITORY
                                </Label>
                                <Input
                                    id="repo"
                                    placeholder="my-prompts"
                                    value={formData.github_repo}
                                    onChange={(e) => onFormDataChange("github_repo", e.target.value)}
                                    className="font-mono"
                                />
                            </div>
                        </div>
                    </div>

                    <DialogFooter>
                        <Button
                            variant="outline"
                            onClick={() => setUpdateDialog(false)}
                            className="font-mono"
                        >
                            Cancel
                        </Button>
                        <Button
                            onClick={onUpdateSettings}
                            disabled={updating}
                            className="font-mono uppercase tracking-wider"
                        >
                            {updating ? "Updating..." : "Update"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Disconnect Dialog */}
            <AlertDialog open={disconnectDialog} onOpenChange={setDisconnectDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle className="font-mono text-foreground">Disconnect GitHub</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to disconnect from GitHub? You'll need to
                            reconfigure your connection to continue using Prompt Manager.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel className="font-mono">Cancel</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={onDisconnect}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90 font-mono uppercase tracking-wider"
                        >
                            Disconnect
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
