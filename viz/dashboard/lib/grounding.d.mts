export type Num = { raw?: string; value: number; decimals: number };
export function collectNumbers(value: unknown, out?: number[]): number[];
export function extractNumbers(text: string): Num[];
export function allowedValues(source: unknown): number[];
export function isGrounded(n: Num, allowed: number[]): boolean;
export function splitSentences(text: string): string[];
export function groundText(text: string, allowed: number[]): { text: string; dropped: string[] };
export function groundObject<T>(obj: T, allowed: number[], dropped?: string[]): T;
