import React, { useState, useEffect } from "react";
import { Eye, Plus, Trash2, Edit2, X, CircleHelp } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "sonner";
import {
    getVisionWebhooks, createVisionWebhook,
    updateVisionWebhook, deleteVisionWebhook
} from "@/lib/api";

function HelpLabel({ children, help }) {
    return <div className="flex items-center gap-1"><Label>{children}</Label><TooltipProvider delayDuration={120}><Tooltip><TooltipTrigger asChild><button type="button" aria-label={`Help: ${children}`} className="text-muted-foreground hover:text-foreground"><CircleHelp className="h-3.5 w-3.5" /></button></TooltipTrigger><TooltipContent className="max-w-xs text-xs leading-relaxed">{help}</TooltipContent></Tooltip></TooltipProvider></div>;
}

/**
 * Vision/Doc parsing completion webhooks.
 * Fired once per successfully-parsed attachment with the entity ref + extracted text.
 * Best-effort fire-once delivery (no retries).
 */
export function VisionWebhooksSettings() {
    const [webhooks, setWebhooks] = useState([]);
    const [loading, setLoading] = useState(true);

    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [formData, setFormData] = useState({
        name: "",
        url: "",
        is_active: true,
        doc_type_filter: "",   // comma-separated mime types; empty = all
        source_filter: "",     // comma-separated source values; empty = all
    });
    const [isSubmitting, setIsSubmitting] = useState(false);

    useEffect(() => { fetchHooks(); }, []);

    const fetchHooks = async () => {
        try {
            const res = await getVisionWebhooks();
            setWebhooks(res.data.vision_webhooks || []);
        } catch (err) {
            toast.error("Failed to fetch vision webhooks");
        } finally {
            setLoading(false);
        }
    };

    const handleToggle = async (id, currentVal) => {
        try {
            await updateVisionWebhook(id, { is_active: !currentVal });
            toast.success(currentVal ? "Webhook disabled" : "Webhook enabled");
            fetchHooks();
        } catch (err) {
            toast.error("Failed to update status");
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm("Delete this vision webhook?")) return;
        try {
            await deleteVisionWebhook(id);
            toast.success("Webhook deleted");
            fetchHooks();
        } catch (err) {
            toast.error("Failed to delete webhook");
        }
    };

    const openCreateDialog = () => {
        setEditingId(null);
        setFormData({
            name: "",
            url: "",
            is_active: true,
            doc_type_filter: "",
            source_filter: "",
        });
        setIsDialogOpen(true);
    };

    const openEditDialog = (wh) => {
        setEditingId(wh.id);
        setFormData({
            name: wh.name,
            url: wh.url,
            is_active: wh.is_active,
            doc_type_filter: Array.isArray(wh.doc_type_filter) ? wh.doc_type_filter.join(",") : "",
            source_filter: Array.isArray(wh.source_filter) ? wh.source_filter.join(",") : "",
        });
        setIsDialogOpen(true);
    };

    const onSubmit = async () => {
        if (!formData.name || !formData.url) {
            toast.error("Name and URL are required");
            return;
        }
        setIsSubmitting(true);
        const docTypes = (formData.doc_type_filter || "").split(",").map(s => s.trim()).filter(Boolean);
        const sources = (formData.source_filter || "").split(",").map(s => s.trim()).filter(Boolean);

        const payload = {
            name: formData.name,
            url: formData.url,
            is_active: formData.is_active,
            doc_type_filter: docTypes.length ? docTypes : null,
            source_filter: sources.length ? sources : null,
        };

        try {
            if (editingId) {
                await updateVisionWebhook(editingId, payload);
                toast.success("Webhook updated");
            } else {
                await createVisionWebhook(payload);
                toast.success("Webhook created");
            }
            setIsDialogOpen(false);
            fetchHooks();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to save webhook");
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <Card>
            <CardHeader className="pb-3 flex flex-row items-start justify-between">
                <div>
                    <div className="flex items-center gap-2">
                        <Eye className="w-5 h-5 text-purple-400" />
                        <CardTitle className="text-lg">Vision Completion Webhooks</CardTitle>
                    </div>
                    <CardDescription className="text-xs mt-1.5">
                        Fired once per successfully-parsed attachment. Payload includes entity ref, doc URL, and the extracted text. Best-effort fire-once delivery.
                    </CardDescription>
                </div>
                <Button size="sm" onClick={openCreateDialog} className="gap-1.5">
                    <Plus className="w-4 h-4" /> Add Webhook
                </Button>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <div className="text-xs text-muted-foreground">Loading webhooks...</div>
                ) : webhooks.length === 0 ? (
                    <div className="text-center py-6 border border-dashed rounded-md bg-secondary/20">
                        <p className="text-sm text-muted-foreground">No vision webhooks configured.</p>
                        <p className="text-xs text-muted-foreground mt-1">Configure endpoints that need parsed-attachment text in real time.</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {webhooks.map(wh => (
                            <div key={wh.id} className="flex flex-col gap-3 p-4 border rounded-md bg-card shadow-sm">
                                <div className="flex items-start justify-between">
                                    <div className="space-y-1">
                                        <div className="flex items-center gap-2">
                                            <h4 className="font-medium text-sm">{wh.name}</h4>
                                            {!wh.is_active && <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded">Disabled</span>}
                                        </div>
                                        <p className="text-xs font-mono text-muted-foreground break-all">{wh.url}</p>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <Switch checked={wh.is_active} onCheckedChange={() => handleToggle(wh.id, wh.is_active)} />
                                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEditDialog(wh)}>
                                            <Edit2 className="w-4 h-4" />
                                        </Button>
                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-red-500" onClick={() => handleDelete(wh.id)}>
                                            <Trash2 className="w-4 h-4" />
                                        </Button>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs border-t pt-3">
                                    <div>
                                        <span className="text-muted-foreground block text-[10px]">Doc Type Filter</span>
                                        <span className="font-medium">{Array.isArray(wh.doc_type_filter) && wh.doc_type_filter.length ? wh.doc_type_filter.join(", ") : "all"}</span>
                                    </div>
                                    <div>
                                        <span className="text-muted-foreground block text-[10px]">Source Filter</span>
                                        <span className="font-medium">{Array.isArray(wh.source_filter) && wh.source_filter.length ? wh.source_filter.join(", ") : "all"}</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>

            <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                <DialogContent className="max-w-xl">
                    <DialogHeader>
                        <DialogTitle>{editingId ? "Edit Vision Webhook" : "Create Vision Webhook"}</DialogTitle>
                        <DialogDescription>
                            POST'd once per successfully-parsed attachment. Payload: entity_type, entity_id, interaction_id, doc_url, filename, mime_type, source, parsed_text, parsed_at.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto px-1">
                        <div className="space-y-2">
                            <HelpLabel help="A human-readable name used only in this dashboard to identify the completion webhook.">Internal Name</HelpLabel>
                            <Input
                                placeholder="eg. Doc Indexer"
                                value={formData.name}
                                onChange={e => setFormData({ ...formData, name: e.target.value })}
                            />
                        </div>

                        <div className="space-y-2">
                            <HelpLabel help="HTTPS endpoint that receives the parsed-attachment completion payload.">Target URL</HelpLabel>
                            <Input
                                placeholder="https://..."
                                value={formData.url}
                                onChange={e => setFormData({ ...formData, url: e.target.value })}
                            />
                        </div>

                        <div className="space-y-2">
                            <HelpLabel help="Comma-separated MIME types to send, such as application/pdf. Leave empty to send every successfully parsed attachment.">Doc Type Filter</HelpLabel>
                            <Input
                                placeholder="application/pdf,image/png,image/jpeg"
                                className="font-mono text-xs"
                                value={formData.doc_type_filter}
                                onChange={e => setFormData({ ...formData, doc_type_filter: e.target.value })}
                            />
                            <p className="text-[10px] text-muted-foreground">Comma-separated MIME types. Empty = all.</p>
                        </div>

                        <div className="space-y-2">
                            <HelpLabel help="Comma-separated interaction source values to send, such as chatwoot or crm. Leave empty for every source.">Source Filter</HelpLabel>
                            <Input
                                placeholder="chatwoot,crm"
                                className="font-mono text-xs"
                                value={formData.source_filter}
                                onChange={e => setFormData({ ...formData, source_filter: e.target.value })}
                            />
                            <p className="text-[10px] text-muted-foreground">Comma-separated interaction.source values. Empty = all.</p>
                        </div>

                        <div className="flex items-center justify-between border-y py-3">
                            <div className="space-y-0.5">
                                <HelpLabel help="When disabled, attachments are still processed and stored, but no completion webhook is sent.">Active</HelpLabel>
                                <p className="text-[10px] text-muted-foreground">When off, parsed attachments are stored but no POST is sent.</p>
                            </div>
                            <Switch
                                checked={formData.is_active}
                                onCheckedChange={v => setFormData({ ...formData, is_active: v })}
                            />
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setIsDialogOpen(false)}>Cancel</Button>
                        <Button onClick={onSubmit} disabled={isSubmitting}>
                            {isSubmitting ? "Saving..." : "Save Config"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Card>
    );
}
