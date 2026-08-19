import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { appliedProposal, auditEntry, pendingProposal } from "../test-fixtures";
import { ProposalCard } from "./ProposalCard";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ProposalCard", () => {
  it("renders pending proposal with agent, target, diff, and reasoning", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderWithClient(<ProposalCard item={pendingProposal} />);

    expect(screen.getByText("lead_tagger")).toBeInTheDocument();
    expect(screen.getByText(/Jane Testerly/)).toBeInTheDocument();
    expect(screen.getByText(pendingProposal.proposal.reasoning)).toBeInTheDocument();

    const existingPill = screen.getByText("newsletter");
    const addedPill = screen.getByText("+hot-lead");
    expect(existingPill).toBeInTheDocument();
    expect(addedPill.textContent).toMatch(/^\+/);
    expect(addedPill.className).not.toBe(existingPill.className);

    expect(screen.getByRole("button", { name: /approve/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /reject/i })).toBeEnabled();
  });

  it("approve click posts to the approve endpoint and disables the button", async () => {
    let resolveFetch!: (value: Response) => void;
    const deferred = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    const fetchMock = vi.fn().mockReturnValue(deferred);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithClient(<ProposalCard item={pendingProposal} />);

    const approve = screen.getByRole("button", { name: /approve/i });
    await user.click(approve);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit | undefined];
    expect(String(url)).toContain("/proposals/prop_test001/approve");
    expect(init?.method).toBe("POST");
    await waitFor(() => expect(approve).toBeDisabled());

    resolveFetch(jsonResponse(appliedProposal));
  });

  it("reject click posts to the reject endpoint", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ ...pendingProposal, status: "rejected" }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithClient(<ProposalCard item={pendingProposal} />);

    await user.click(screen.getByRole("button", { name: /reject/i }));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit | undefined];
    expect(String(url)).toContain("/proposals/prop_test001/reject");
    expect(init?.method).toBe("POST");
  });

  it("applied card shows its audit entry instead of buttons", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/audit")) {
        return Promise.resolve(jsonResponse({ entries: [auditEntry] }));
      }
      return Promise.reject(new Error(`unexpected fetch: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithClient(<ProposalCard item={appliedProposal} />);

    expect(await screen.findByText(/mode api/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reject/i })).not.toBeInTheDocument();
  });
});
