import React from "react";
import { Database, Plus, Trash2, Tag, BookOpen, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from "@/components/ui/dialog";

export function KnowledgeModelSettings({
    entityTypes,
    lessonTypes,
    channelTypes,
    newType,
    setNewType,
    addTypeDialogOpen,
    setAddTypeDialogOpen,
    onAddType,
    onDeleteType,
    loading
}) {
    const sections = [
        { title: "Entity Types", icon: Tag, data: entityTypes, type: "entity", description: "Categories of things the system tracks (e.g. Person, Company, Project)" },
        { title: "Lesson Types", icon: BookOpen, data: lessonTypes, type: "lesson", description: "Types of insights or lessons extracted (e.g. Best Practice, Warning, Technical)" },
        { title: "Channel Types", icon: MessageSquare, data: channelTypes, type: "channel", description: "Sources of information (e.g. Slack, Email, Meeting)" },
    ];

    return (
        <div className="space-y-6 max-w-4xl">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {sections.map((section) => {
                    const Icon = section.icon;
                    return (
                        <Card key={section.type}>
                            <CardHeader className="pb-3">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <Icon className="w-5 h-5 text-primary" />
                                        <CardTitle className="text-lg">{section.title}</CardTitle>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => {
                                            setNewType({ name: "", description: "", type: section.type });
                                            setAddTypeDialogOpen(true);
                                        }}
                                    >
                                        <Plus className="w-4 h-4" />
                                    </Button>
                                </div>
                                <CardDescription className="text-xs">{section.description}</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    {section.data.length === 0 ? (
                                        <p className="text-xs text-muted-foreground py-4 text-center border border-dashed rounded-lg">
                                            No {section.title.toLowerCase()} defined.
                                        </p>
                                    ) : (
                                        section.data.map((item) => (
                                            <div key={item.id} className="flex items-center justify-between p-2 rounded border bg-card/50 text-sm">
                                                <div className="min-w-0">
                                                    <p className="font-medium truncate">{item.name || item.label}</p>
                                                    <p className="text-[10px] text-muted-foreground truncate">{item.description}</p>
                                                </div>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                                                    onClick={() => onDeleteType(section.type, item.id)}
                                                >
                                                    <Trash2 className="w-3.5 h-3.5" />
                                                </Button>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    );
                })}
            </div>

            <Dialog open={addTypeDialogOpen} onOpenChange={setAddTypeDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Add {newType.type?.charAt(0).toUpperCase() + newType.type?.slice(1)} Type</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div className="space-y-2">
                            <Label>Name</Label>
                            <Input
                                value={newType.name}
                                onChange={(e) => setNewType({ ...newType, name: e.target.value })}
                                placeholder="e.g. Project"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Description</Label>
                            <Input
                                value={newType.description}
                                onChange={(e) => setNewType({ ...newType, description: e.target.value })}
                                placeholder="Brief description..."
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setAddTypeDialogOpen(false)}>Cancel</Button>
                        <Button onClick={onAddType} disabled={!newType.name.trim()}>Add Type</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
