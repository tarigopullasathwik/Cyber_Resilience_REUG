import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge, DataTable, Progress, Stat, StatusBadge } from "./ui";

describe("UI primitives", () => {
  it("renders a stat with label, value and hint", () => {
    render(<Stat label="F1-score" value="0.914" hint="held-out test" tone="cyan" />);
    expect(screen.getByText("F1-score")).toBeInTheDocument();
    expect(screen.getByText("0.914")).toBeInTheDocument();
    expect(screen.getByText("held-out test")).toBeInTheDocument();
  });

  it("renders status badges and progress values", () => {
    render(<StatusBadge status="CONTAINED" />);
    render(<Progress value={0.42} message="Fitting model" />);
    expect(screen.getByText("CONTAINED")).toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("Fitting model")).toBeInTheDocument();
  });

  it("renders an empty table message", () => {
    render(<DataTable columns={[{ key: "name", label: "Name" }]} rows={[]} empty="Nothing here yet." />);
    expect(screen.getByText("Nothing here yet.")).toBeInTheDocument();
    render(<Badge tone="amber">withheld</Badge>);
    expect(screen.getByText("withheld")).toBeInTheDocument();
  });
});
