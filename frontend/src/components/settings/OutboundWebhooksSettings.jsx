import React, { useState, useEffect } from "react";
import { 
    Webhook, Plus, Trash2, Edit2, Check, X, AlertCircle, RefreshCw
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { 
    getOutboundWebhooks, createOutboundWebhook, 
    updateOutboundWebhook, deleteOutboundWebhook 
} from "@/lib/api";

export function OutboundWebhooksSettings() {
    const [webhooks, setWebhooks] = useState([]);
    const [loading, setLoading] = useState(true);
    
    // Dialog State
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [editingHookId, setEditingHookId] = useState(null);
    const [formData, setFormData] = useState({
        name: "",
        url: "",
        debounce_ms: 60000,
        payload_mode: "trigger_only",
        include_latest_memory: true,
        conditions: [] // [{key: "", value: ""}] internally for UI
    });
    const [isSubmitting, setIsSubmitting] = useState(false);

    useEffect(() => {
        fetchWebhooks();
    }, []);

    const fetchWebhooks = async () => {
        try {
            const res = await getOutboundWebhooks();
            setWebhooks(res.data.outbound_webhooks || []);
        } catch (err) {
            toast.error("Failed to fetch outbound webhooks");
        } finally {
            setLoading(false);
        }
    };

    const handleToggleActive = async (id, currentVal) => {
        try {
            await updateOutboundWebhook(id, { is_active: !currentVal });
            toast.success(currentVal ? "Webhook disabled" : "Webhook enabled");
            fetchWebhooks();
        } catch (err) {
            toast.error("Failed to update status");
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm("Delete this webhook rule?")) return;
        try {
            await deleteOutboundWebhook(id);
            toast.success("Webhook deleted");
            fetchWebhooks();
        } catch (err) {
            toast.error("Failed to delete webhook");
        }
    };

    const openCreateDialog = () => {
        setEditingHookId(null);
        setFormData({
            name: "",
            url: "",
            debounce_ms: 60000,
            payload_mode: "trigger_only",
            include_latest_memory: true,
            conditions: [{ key: "interaction_type", value: "whatsapp_incoming" }]
        });
        setIsDialogOpen(true);
    };

    const openEditDialog = (wh) => {
        setEditingHookId(wh.id);
        
        // Convert dictionary conditions to array for UI
        let condsArr = [];
        if (wh.conditions && Object.keys(wh.conditions).length > 0) {
            condsArr = Object.entries(wh.conditions).map(([k, v]) => ({
                key: k,
                value: Array.isArray(v) ? v.join(",") : v
            }));
        } else {
            condsArr = [{ key: "", value: "" }];
        }

        setFormData({
            name: wh.name,
            url: wh.url,
            debounce_ms: wh.debounce_ms || 60000,
            payload_mode: wh.payload_mode || "trigger_only",
            include_latest_memory: wh.include_latest_memory,
            conditions: condsArr
        });
        setIsDialogOpen(true);
    };

    const handleAddCondition = () => {
        setFormData(prev => ({
            ...prev,
            conditions: [...prev.conditions, { key: "", value: "" }]
        }));
    };

    const handleUpdateCondition = (index, field, value) => {
        const newConds = [...formData.conditions];
        newConds[index][field] = value;
        setFormData(prev => ({ ...prev, conditions: newConds }));
    };

    const handleRemoveCondition = (index) => {
        const newConds = [...formData.conditions];
        newConds.splice(index, 1);
        setFormData(prev => ({ ...prev, conditions: newConds }));
    };

    const onSubmit = async () => {
        if (!formData.name || !formData.url) {
            toast.error("Name and URL are required");
            return;
        }

        setIsSubmitting(true);
        // Pack UI conditions back to dictionary
        const finalConditions = {};
        formData.conditions.forEach(c => {
            const k = c.key.trim();
            const v = c.value.trim();
            if (k) {
                // if comma separated, send as array to backend
                if (v.includes(",")) {
                    finalConditions[k] = v.split(",").map(s => s.trim());
                } else {
                    finalConditions[k] = v;
                }
            }
        });

        const payload = {
            name: formData.name,
            url: formData.url,
            debounce_ms: formData.debounce_ms,
            payload_mode: formData.payload_mode,
            include_latest_memory: formData.include_latest_memory,
            conditions: finalConditions
        };

        try {
            if (editingHookId) {
                await updateOutboundWebhook(editingHookId, payload);
                toast.success("Webhook updated successfully");
            } else {
                await createOutboundWebhook(payload);
                toast.success("Webhook created successfully");
            }
            setIsDialogOpen(false);
            fetchWebhooks();
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
                        <Webhook className="w-5 h-5 text-indigo-400" />
                        <CardTitle className="text-lg">Outbound Rule Engine</CardTitle>
                    </div>
                    <CardDescription className="text-xs mt-1.5">
                        Trigger external workflows after incoming interactions are fully parsed and enriched
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
                        <p className="text-sm text-muted-foreground">No outbound webhooks configured.</p>
                        <p className="text-xs text-muted-foreground mt-1">Configure endpoints to react to enriched data (like Make.com or Zapier).</p>
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
                                        <Switch 
                                            checked={wh.is_active} 
                                            onCheckedChange={() => handleToggleActive(wh.id, wh.is_active)} 
                                        />
                                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEditDialog(wh)}>
                                            <Edit2 className="w-4 h-4" />
                                        </Button>
                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-red-500" onClick={() => handleDelete(wh.id)}>
                                            <Trash2 className="w-4 h-4" />
                                        </Button>
                                    </div>
                                </div>
                                
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs border-t pt-3">
                                    <div>
                                        <span className="text-muted-foreground block text-[10px]">Debounce Window</span>
                                        <span className="font-medium">{wh.debounce_ms / 1000} seconds</span>
                                    </div>
                                    <div>
                                        <span className="text-muted-foreground block text-[10px]">Payload Filters</span>
                                        <span className="font-medium">{Object.keys(wh.conditions || {}).length} rules</span>
                                    </div>
                                    <div>
                                        <span className="text-muted-foreground block text-[10px]">Mode</span>
                                        <span className="font-medium">{wh.payload_mode === 'all_window' ? 'Timeline Context' : 'Strict Trigger'}</span>
                                    </div>
                                    <div>
                                        <span className="text-muted-foreground block text-[10px]">Memory Link</span>
                                        <span className="font-medium">{wh.include_latest_memory ? 'Yes' : 'No'}</span>
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
                        <DialogTitle>{editingHookId ? "Edit Webhook" : "Create Webhook"}</DialogTitle>
                        <DialogDescription>
                            Configure exactly when and how this external endpoint should be triggered.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto px-1">
                        <div className="space-y-2">
                            <Label>Internal Name</Label>
                            <Input 
                                placeholder="eg. Make.com WhatsApp Responder" 
                                value={formData.name}
                                onChange={e => setFormData({...formData, name: e.target.value})}
                            />
                        </div>
                        
                        <div className="space-y-2">
                            <Label>Target URL</Label>
                            <Input 
                                placeholder="https://hook.make.com/..." 
                                value={formData.url}
                                onChange={e => setFormData({...formData, url: e.target.value})}
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Debounce Time (ms)</Label>
                                <Input 
                                    type="number"
                                    min={5000}
                                    value={formData.debounce_ms}
                                    onChange={e => setFormData({...formData, debounce_ms: parseInt(e.target.value) || 60000})}
                                />
                                <p className="text-[10px] text-muted-foreground">Wait N ms after the last message to allow for rapid-fire "settling".</p>
                            </div>
                            
                            <div className="space-y-2">
                                <Label>Payload Composition</Label>
                                <Select 
                                    value={formData.payload_mode} 
                                    onValueChange={v => setFormData({...formData, payload_mode: v})}
                                >
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="trigger_only">Strict Filter (Only matching types)</SelectItem>
                                        <SelectItem value="all_window">Timeline Context (All in window)</SelectItem>
                                    </SelectContent>
                                </Select>
                                <p className="text-[10px] text-muted-foreground">What interactions get bundled into the array when the timer pops.</p>
                            </div>
                        </div>

                        <div className="flex items-center justify-between border-y py-3 my-2">
                            <div className="space-y-0.5">
                                <Label>Include Latest Memory</Label>
                                <p className="text-[10px] text-muted-foreground">Attach the Entity's latest compacted knowledge base.</p>
                            </div>
                            <Switch 
                                checked={formData.include_latest_memory} 
                                onCheckedChange={v => setFormData({...formData, include_latest_memory: v})}
                            />
                        </div>

                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <Label>Trigger Conditions</Label>
                                <Button variant="outline" size="sm" className="h-7 text-[10px]" onClick={handleAddCondition}>
                                    <Plus className="w-3 h-3 mr-1" /> Add Rule
                                </Button>
                            </div>
                            
                            {formData.conditions.length === 0 && (
                                <div className="text-[10px] text-amber-500 italic">No conditions set! This will trigger on EVERY interaction.</div>
                            )}

                            {formData.conditions.map((cond, i) => (
                                <div key={i} className="flex items-center gap-2 bg-secondary/30 p-2 rounded relative group">
                                    <Input 
                                        placeholder="Field (e.g. interaction_type)" 
                                        className="h-8 text-xs font-mono"
                                        value={cond.key}
                                        onChange={e => handleUpdateCondition(i, 'key', e.target.value)}
                                    />
                                    <span className="text-muted-foreground text-xs">=</span>
                                    <Input 
                                        placeholder="Value (match1,match2)" 
                                        className="h-8 text-xs font-mono"
                                        value={cond.value}
                                        onChange={e => handleUpdateCondition(i, 'value', e.target.value)}
                                    />
                                    <Button variant="ghost" size="icon" className="h-8 w-8 text-red-500 shrink-0" onClick={() => handleRemoveCondition(i)}>
                                        <X className="w-4 h-4" />
                                    </Button>
                                </div>
                            ))}
                            <p className="text-[10px] text-muted-foreground mt-1">If multiple rules are added, ALL Must match (AND). Use commas in Value for OR matching.</p>
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
