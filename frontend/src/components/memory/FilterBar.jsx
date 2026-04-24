import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { MultiSelect } from "@/components/ui/multi-select";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function FilterBar({
  appliedFilter, setAppliedFilter,
  entityIdInput, setEntityIdInput,
  filterOptions,
}) {
  return (
    <Card className="bg-card">
      <CardContent className="p-4 flex flex-wrap gap-4 items-end">
        <div className="space-y-1">
          <Label>Entity Type</Label>
          <MultiSelect
            options={filterOptions.entity_types}
            selected={appliedFilter.entity_types}
            onChange={(val) => setAppliedFilter({ ...appliedFilter, entity_types: val })}
            placeholder="All Entity Types"
            className="w-48"
          />
        </div>
        <div className="space-y-1">
          <Label>Interaction Type</Label>
          <MultiSelect
            options={filterOptions.interaction_types}
            selected={appliedFilter.interaction_types}
            onChange={(val) => setAppliedFilter({ ...appliedFilter, interaction_types: val })}
            placeholder="All Interaction Types"
            className="w-64"
          />
        </div>
        <div className="space-y-1">
          <Label>Time Range</Label>
          <Select value={appliedFilter.time_range} onValueChange={(v) => setAppliedFilter({ ...appliedFilter, time_range: v })}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Time</SelectItem>
              <SelectItem value="last_24h">Last 24 Hours</SelectItem>
              <SelectItem value="last_3d">Last 3 Days</SelectItem>
              <SelectItem value="last_7d">Last 7 Days</SelectItem>
              <SelectItem value="last_30d">Last 30 Days</SelectItem>
              <SelectItem value="last_60d">Last 60 Days</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1 flex-1 min-w-[200px]">
          <Label>Entity ID (Debounced text filter)</Label>
          <Input
            placeholder="Start typing specific entity ID (min 3 chars)..."
            value={entityIdInput}
            onChange={(e) => setEntityIdInput(e.target.value)}
          />
        </div>
      </CardContent>
    </Card>
  );
}
