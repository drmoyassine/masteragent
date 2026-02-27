import { useState, useRef, useEffect, useCallback } from "react";
import { Building, FileText, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

/**
 * VariableAutocomplete Component
 * 
 * A textarea wrapper that provides @-triggered autocomplete for variables.
 * When user types @, shows a popover with available variables from both
 * prompt-level and account-level sources.
 * 
 * @param {string} value - The textarea content
 * @param {function} onChange - Callback when content changes
 * @param {array} variables - Array of available variables with {name, source, value, description}
 * @param {string} placeholder - Placeholder text for textarea
 * @param {string} className - Additional CSS classes
 * @param {object} props - Additional props passed to textarea
 */
export default function VariableAutocomplete({
  value,
  onChange,
  variables = [],
  placeholder = "Write your content here... Use @ to insert variables",
  className = "",
  ...props
}) {
  const textareaRef = useRef(null);
  const containerRef = useRef(null);
  const [showPopover, setShowPopover] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [triggerPosition, setTriggerPosition] = useState({ top: 0, left: 0 });
  const [triggerIndex, setTriggerIndex] = useState(-1);
  
  // Debug: log variables to diagnose empty array issues
  useEffect(() => {
    console.log("[VariableAutocomplete] Variables received:", variables);
    console.log("[VariableAutocomplete] Variables count:", variables?.length || 0);
    if (variables && variables.length > 0) {
      console.log("[VariableAutocomplete] First variable:", variables[0]);
    }
  }, [variables]);
  
  // Separate variables by source
  const promptVariables = variables.filter(v => v.source === "prompt");
  const accountVariables = variables.filter(v => v.source === "account");
  
  // Debug: log filtered variables
  useEffect(() => {
    console.log("[VariableAutocomplete] Prompt vars:", promptVariables.length, "Account vars:", accountVariables.length);
  }, [promptVariables.length, accountVariables.length]);
  
  // Filter variables based on search query
  const filteredPromptVars = promptVariables.filter(v => 
    v.name.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const filteredAccountVars = accountVariables.filter(v =>
    v.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Handle input changes and detect @ trigger
  const handleInput = (e) => {
    const newValue = e.target.value;
    const { selectionStart } = e.target;
    
    console.log("[VariableAutocomplete] Input event, key typed:", newValue[selectionStart - 1], "position:", selectionStart);
    
    onChange(e);
    
    // Check if we just typed @
    if (newValue[selectionStart - 1] === "@") {
      // Check if @ is at start or preceded by whitespace or newline
      const prevChar = selectionStart > 1 ? newValue[selectionStart - 2] : "";
      console.log("[VariableAutocomplete] @ detected, prevChar:", JSON.stringify(prevChar), "selectionStart:", selectionStart);
      console.log("[VariableAutocomplete] Condition check - selectionStart === 1:", selectionStart === 1, "whitespace test:", /\s|\n/.test(prevChar));
      if (selectionStart === 1 || /\s|\n/.test(prevChar)) {
        console.log("[VariableAutocomplete] Showing popover, variables count:", variables?.length || 0);
        console.log("[VariableAutocomplete] Current variables:", variables);
        setTriggerIndex(selectionStart - 1);
        setSearchQuery("");
        const position = calculateCursorPosition();
        console.log("[VariableAutocomplete] Cursor position calculated:", position);
        setTriggerPosition(position);
        setShowPopover(true);
        console.log("[VariableAutocomplete] setShowPopover(true) called");
      }
    } else if (showPopover && triggerIndex !== -1) {
      // Update search query based on text after @
      const textAfterTrigger = newValue.substring(triggerIndex + 1, selectionStart);
      if (textAfterTrigger.includes(" ") || textAfterTrigger.includes("\n")) {
        // Close popover if space or newline is typed
        setShowPopover(false);
        setTriggerIndex(-1);
      } else {
        setSearchQuery(textAfterTrigger);
      }
    }
  };

  // Handle variable selection
  const insertVariable = (variableName) => {
    if (!textareaRef.current || triggerIndex === -1) return;
    
    const textarea = textareaRef.current;
    const { selectionStart } = textarea;
    
    // Find the end of the @query
    let queryEnd = triggerIndex + 1;
    while (queryEnd < value.length && !/\s|\n/.test(value[queryEnd])) {
      queryEnd++;
    }
    
    // Build new value: text before @ + {{variable}} + text after query
    const beforeTrigger = value.substring(0, triggerIndex);
    const afterQuery = value.substring(queryEnd);
    const variableSyntax = `{{${variableName}}}`;
    const newValue = beforeTrigger + variableSyntax + afterQuery;
    
    // Create synthetic event
    const syntheticEvent = {
      target: {
        value: newValue,
        selectionStart: beforeTrigger.length + variableSyntax.length,
        selectionEnd: beforeTrigger.length + variableSyntax.length,
      },
    };
    
    onChange(syntheticEvent);
    
    // Set cursor position after the inserted variable
    setTimeout(() => {
      const newPos = beforeTrigger.length + variableSyntax.length;
      textarea.setSelectionRange(newPos, newPos);
      textarea.focus();
    }, 0);
    
    setShowPopover(false);
    setTriggerIndex(-1);
    setSearchQuery("");
  };

  // Handle keyboard navigation
  const handleKeyDown = (e) => {
    if (!showPopover) {
      // Check for Escape to close any accidental triggers
      if (e.key === "Escape") {
        setShowPopover(false);
        setTriggerIndex(-1);
      }
      return;
    }
    
    if (e.key === "Escape") {
      e.preventDefault();
      setShowPopover(false);
      setTriggerIndex(-1);
    }
    // Let Command component handle navigation
  };

  // Close popover when clicking outside
  const handleBlur = (e) => {
    // Don't close if clicking inside popover
    if (e.relatedTarget?.closest("[data-radix-popper-content-wrapper]")) {
      return;
    }
    
    // Delay close to allow for selection
    setTimeout(() => {
      setShowPopover(false);
      setTriggerIndex(-1);
    }, 200);
  };

  // Handle paste to reset trigger state
  const handlePaste = () => {
    setShowPopover(false);
    setTriggerIndex(-1);
  };

  // Debug: log render state
  useEffect(() => {
    console.log("[VariableAutocomplete] Render state - showPopover:", showPopover, "triggerIndex:", triggerIndex, "searchQuery:", searchQuery);
  }, [showPopover, triggerIndex, searchQuery]);

  // Calculate cursor position relative to container (not viewport)
  const calculateCursorPosition = useCallback(() => {
    if (!textareaRef.current || !containerRef.current) return { top: 0, left: 0 };
    
    const textarea = textareaRef.current;
    const container = containerRef.current;
    const { selectionStart } = textarea;
    const textareaRect = textarea.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    
    // Create a hidden div to measure text position
    const div = document.createElement("div");
    const style = window.getComputedStyle(textarea);
    
    div.style.position = "absolute";
    div.style.visibility = "hidden";
    div.style.whiteSpace = "pre-wrap";
    div.style.wordWrap = "break-word";
    div.style.width = style.width;
    div.style.font = style.font;
    div.style.padding = style.padding;
    div.style.border = style.border;
    div.style.boxSizing = style.boxSizing;
    div.style.lineHeight = style.lineHeight;
    div.style.top = "0";
    div.style.left = "0";
    
    // Get text up to cursor
    const textBeforeCursor = value.substring(0, selectionStart);
    div.textContent = textBeforeCursor;
    
    document.body.appendChild(div);
    
    // Add a span to measure cursor position
    const span = document.createElement("span");
    span.textContent = "|";
    div.appendChild(span);
    
    // Get the span's position within the measurement div
    const spanOffsetLeft = span.offsetLeft;
    const spanOffsetTop = span.offsetTop;
    const spanHeight = span.offsetHeight;
    
    document.body.removeChild(div);
    
    // Calculate position relative to container
    // Top: measured position from textarea top + textarea offset from container
    const lineHeight = parseInt(style.lineHeight) || 20;
    const paddingTop = parseInt(style.paddingTop) || 0;
    const paddingLeft = parseInt(style.paddingLeft) || 0;
    
    // Position relative to container: textarea position within container + cursor position within textarea
    const textareaTopInContainer = textareaRect.top - containerRect.top;
    const textareaLeftInContainer = textareaRect.left - containerRect.left;
    
    // Calculate cursor position relative to textarea content
    let top = textareaTopInContainer + paddingTop + spanOffsetTop - textarea.scrollTop + spanHeight;
    let left = textareaLeftInContainer + paddingLeft + spanOffsetLeft - textarea.scrollLeft;
    
    // Clamp to ensure popover stays within reasonable bounds
    const minLeft = 10;
    const maxLeft = containerRect.width - 280; // 280px is popover width + buffer
    left = Math.max(minLeft, Math.min(left, maxLeft));
    
    // Ensure top doesn't go negative
    top = Math.max(10, top);
    
    console.log("[VariableAutocomplete] Position calc - relative to container:", { top, left });
    
    return { top, left };
  }, [value]);

  return (
    <div ref={containerRef} className="relative w-full h-full">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        onPaste={handlePaste}
        className={className}
        placeholder={placeholder}
        {...props}
        data-testid="variable-autocomplete-textarea"
      />
      
      {/* Autocomplete Popover */}
      <Popover open={showPopover} onOpenChange={setShowPopover}>
        <PopoverTrigger asChild>
          <span
            className="absolute w-0 h-0"
            style={{
              top: triggerPosition.top,
              left: triggerPosition.left,
            }}
          />
        </PopoverTrigger>
        <PopoverContent
          className="w-64 p-0 z-50"
          align="start"
          side="bottom"
          sideOffset={5}
          onOpenAutoFocus={(e) => e.preventDefault()}
          onEscapeKeyDown={() => {
            setShowPopover(false);
            setTriggerIndex(-1);
          }}
          data-testid="variable-popover"
        >
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Search variables..."
              value={searchQuery}
              onValueChange={setSearchQuery}
              className="h-8"
            />
            <CommandList className="max-h-64">
              <CommandEmpty>No variables found.</CommandEmpty>
              
              {/* Prompt Variables */}
              {filteredPromptVars.length > 0 && (
                <CommandGroup heading="Prompt Variables">
                  {filteredPromptVars.map((variable) => (
                    <CommandItem
                      key={`prompt-${variable.name}`}
                      onSelect={() => insertVariable(variable.name)}
                      className="flex items-center justify-between"
                      data-testid={`variable-option-prompt-${variable.name}`}
                    >
                      <div className="flex items-center gap-2">
                        <FileText className="w-3 h-3 text-muted-foreground" />
                        <code className="text-sm font-mono">
                          {variable.name}
                        </code>
                      </div>
                      {variable.value && (
                        <span className="text-xs text-muted-foreground truncate max-w-24">
                          {variable.value}
                        </span>
                      )}
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
              
              {/* Separator if both groups have items */}
              {filteredPromptVars.length > 0 && filteredAccountVars.length > 0 && (
                <CommandSeparator />
              )}
              
              {/* Account Variables */}
              {filteredAccountVars.length > 0 && (
                <CommandGroup heading="Account Variables">
                  {filteredAccountVars.map((variable) => (
                    <CommandItem
                      key={`account-${variable.name}`}
                      onSelect={() => insertVariable(variable.name)}
                      className="flex items-center justify-between"
                      data-testid={`variable-option-account-${variable.name}`}
                    >
                      <div className="flex items-center gap-2">
                        <Building className="w-3 h-3 text-muted-foreground" />
                        <code className="text-sm font-mono">
                          {variable.name}
                        </code>
                      </div>
                      {variable.value && (
                        <span className="text-xs text-muted-foreground truncate max-w-24">
                          {variable.value}
                        </span>
                      )}
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      
      {/* Helper text */}
      <div className="absolute bottom-2 right-2 text-xs text-muted-foreground pointer-events-none">
        Type @ for variables
      </div>
    </div>
  );
}
