import { describe, expect, it } from "vitest";
import {
  actionTone,
  classForStatus,
  formatBytes,
  formatMetric,
  formatNumber,
  formatPercent,
  normalizeStatus,
  titleCase,
} from "./format";

describe("format helpers", () => {
  it("formats numbers and metrics with a stable fallback", () => {
    expect(formatNumber(12345)).toBe("12,345");
    expect(formatMetric(0.9137)).toBe("0.914");
    expect(formatPercent(0.0432)).toBe("4.3%");
    expect(formatMetric(null)).toBe("—");
    expect(formatNumber(Number.NaN)).toBe("—");
  });

  it("formats bytes and titles", () => {
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(4 * 1024 * 1024)).toBe("4.0 MB");
    expect(titleCase("port_scan")).toBe("Port Scan");
  });

  it("maps containment states to consistent tones", () => {
    expect(classForStatus("CONTAINED")).toBe("green");
    expect(classForStatus("QUARANTINED")).toBe("red");
    expect(classForStatus("INCONCLUSIVE")).toBe("amber");
    expect(actionTone("QUARANTINE")).toBe("red");
    expect(actionTone("RATE_LIMIT")).toBe("blue");
    expect(normalizeStatus("reauth_required")).toBe("REAUTH REQUIRED");
  });
});
