import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CommandBar } from "@/components/CommandBar";
import { Progress, Score, statusTone } from "@/components/ui";
import { ApiError, errorText } from "@/lib/api";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe("ui primitives", () => {
  it("progress is accessible and clamped", () => {
    render(<Progress value={140} label="Plan progress" />);
    expect(screen.getByRole("progressbar", { name: "Plan progress" })).toHaveAttribute("aria-valuenow", "100");
  });
  it("score shows a dash when there is no value", () => {
    render(<Score value={null} label="Role fit" />);
    expect(screen.getByText("–")).toBeInTheDocument();
  });
  it("maps evidence statuses to tones", () => {
    expect(statusTone("demonstrated")).toBe("good");
    expect(statusTone("missing")).toBe("bad");
    expect(statusTone("something-new")).toBe("neutral");
  });
});

describe("errorText", () => {
  it("lists field validation errors", () => {
    const e = new ApiError(422, "VALIDATION_ERROR", "Some fields are invalid.", { errors: [{ field: "weekly_hours", message: "too big" }] });
    expect(errorText(e)).toBe("weekly_hours: too big");
  });
});

describe("CommandBar (dictation-friendly input)", () => {
  it("interprets text, shows the proposed change and only executes after confirmation", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      calls.push(`${init?.method} ${url}`);
      const body = String(url).endsWith("/commands/interpret")
        ? { understood: true, valid: true, requires_confirmation: true, summary: "Change weekly study time to 8 hours",
            changes: [{ field: "Weekly study hours", from: 6, to: 8 }], action: { type: "set_weekly_hours", params: { hours: 8 } } }
        : { ok: true, type: "set_weekly_hours", summary: "Change weekly study time to 8 hours", result: {} };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    wrap(<CommandBar />);
    await userEvent.type(screen.getByLabelText("Tell PivotPilot what changed"), "I can study 8 hours a week");
    await userEvent.click(screen.getByRole("button", { name: /Interpret/ }));
    expect(await screen.findByText("Change weekly study time to 8 hours")).toBeInTheDocument();
    expect(calls.some((c) => c.includes("/commands/execute"))).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText(/Done: Change weekly study time/)).toBeInTheDocument();
    expect(calls.filter((c) => c.includes("/commands/execute"))).toHaveLength(1);
  });
});
