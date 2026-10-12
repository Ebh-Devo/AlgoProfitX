export function allowedApiBaseUrlsFor(appEnv: string | undefined): string[];
export function webOriginFor(appEnv: string | undefined): string;
export function environmentBuildPlugin(appEnv: string | undefined): import("vite").Plugin;
