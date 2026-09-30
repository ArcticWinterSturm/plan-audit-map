/**
 * @fileoverview Number formatting utilities for cognitive state output.
 */

/**
 * Format a number to 3 significant digits.
 * Examples: 0.7999999999999999 -> "0.800", 0.10000000000000002 -> "0.100"
 */
export function formatNumber(value: number): string {
  if (value === 0) return '0.00';
  if (Number.isInteger(value)) return value.toString();
  
  const absValue = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  
  if (absValue >= 1) {
    return sign + absValue.toFixed(3);
  }
  
  // For values < 1, find significant digits
  let digits = 0;
  let remaining = absValue;
  while (remaining < 1 && digits < 10) {
    remaining *= 10;
    digits++;
  }
  
  const precision = digits + 2;
  return sign + absValue.toFixed(precision);
}

/**
 * Format all numeric values in an object recursively, marking repeated values.
 * Second and subsequent occurrences of the same formatted number ANYWHERE in the 
 * object get "*" appended.
 */
export function formatObjectNumbers(obj: any): any {
  const seen = new Map<string, number>();
  
  function format(value: any): any {
    if (value === null || value === undefined) return value;
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') {
      const formatted = formatNumber(value);
      const existing = seen.get(formatted) || 0;
      seen.set(formatted, existing + 1);
      return existing > 0 ? formatted + '*' : formatted;
    }
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) return value.map(format);
    if (typeof value === 'object') {
      const result: any = {};
      for (const [key, val] of Object.entries(value)) {
        result[key] = format(val);
      }
      return result;
    }
    return value;
  }
  
  return format(obj);
}
