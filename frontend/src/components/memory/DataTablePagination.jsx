import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChevronLeft, ChevronRight } from "lucide-react";

/**
 * Table pagination footer: "Showing a–b of total", Prev/Next, page-size selector.
 * Controlled — parent owns page/pageSize/total.
 */
export default function DataTablePagination({ page, pageSize, total, onPageChange, onPageSizeChange }) {
  const totalPages = total > 0 ? Math.ceil(total / pageSize) : 1;
  const safePage = Math.min(page, totalPages - 1);
  const from = total === 0 ? 0 : safePage * pageSize + 1;
  const to = Math.min((safePage + 1) * pageSize, total);

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between px-1 py-2 text-sm text-muted-foreground">
      <div className="flex items-center gap-3">
        <span>Showing <span className="font-medium text-foreground">{from}</span>–<span className="font-medium text-foreground">{to}</span> of <span className="font-medium text-foreground">{total}</span></span>
        <Select value={String(pageSize)} onValueChange={(v) => onPageSizeChange(Number(v))}>
          <SelectTrigger className="h-8 w-[80px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            {[10, 20, 50, 100].map((n) => (
              <SelectItem key={n} value={String(n)}>{n} / page</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="h-8 gap-1" disabled={safePage <= 0} onClick={() => onPageChange(safePage - 1)}>
          <ChevronLeft className="h-4 w-4" /> Prev
        </Button>
        <span className="text-xs">Page <span className="font-medium text-foreground">{safePage + 1}</span> of {totalPages}</span>
        <Button variant="outline" size="sm" className="h-8 gap-1" disabled={safePage >= totalPages - 1} onClick={() => onPageChange(safePage + 1)}>
          Next <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
