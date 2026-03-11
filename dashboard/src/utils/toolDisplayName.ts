import type { ToolItem } from '@/components/extension/componentPanel/types';

type ToolDisplayNameSource = Pick<ToolItem, 'name' | 'display_name'>;
type ToolSearchSource = Pick<ToolItem, 'name' | 'display_name' | 'description' | 'origin' | 'origin_name'>;

export function resolveToolDisplayName(
    toolName: string,
    availableTools: ToolDisplayNameSource[] = []
): string {
    const tool = availableTools.find(item => item.name === toolName);
    return tool?.display_name || toolName;
}

export function matchesToolSearch(tool: ToolSearchSource, rawQuery: string): boolean {
    const query = rawQuery.trim().toLowerCase();
    if (!query) {
        return true;
    }

    return [
        tool.display_name,
        tool.name,
        tool.description,
        tool.origin,
        tool.origin_name,
    ].some(value => value?.toLowerCase().includes(query));
}