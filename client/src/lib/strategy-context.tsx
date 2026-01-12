import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./api";

type StrategyFileInfo = {
    filename: string;
    path: string;
    size: number;
    mtime: number;
    strategy_hash?: string | null;
};

type SelectedStrategyContextValue = {
    selectedFilename: string | null;
    selectStrategy: (filename: string | null) => void;
    strategyCode: string;
    isLoading: boolean;
};

const SelectedStrategyContext = createContext<SelectedStrategyContextValue | null>(null);

export function useSelectedStrategy() {
    const ctx = useContext(SelectedStrategyContext);
    if (!ctx) throw new Error("useSelectedStrategy must be used within SelectedStrategyProvider");
    return ctx;
}

export function SelectedStrategyProvider({ children }: { children: React.ReactNode }) {
    const [selectedFilename, setSelectedFilename] = useState<string | null>(null);

    // Query to fetch the selected strategy's content
    const { data, isLoading } = useQuery({
        queryKey: ["selected_strategy_content", selectedFilename],
        queryFn: async () => {
            if (!selectedFilename) return null;
            try {
                const response = await apiGet<{ content?: string }>(`/api/strategies/${encodeURIComponent(selectedFilename)}`);
                return response.content || "";
            } catch (e) {
                console.error("Failed to load strategy:", e);
                return "";
            }
        },
        enabled: !!selectedFilename,
        staleTime: 5000,
    });

    const selectStrategy = useCallback((filename: string | null) => {
        setSelectedFilename(filename);
    }, []);

    const strategyCode = data || "";

    return (
        <SelectedStrategyContext.Provider value={{ selectedFilename, selectStrategy, strategyCode, isLoading }}>
            {children}
        </SelectedStrategyContext.Provider>
    );
}
