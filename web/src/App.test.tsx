import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

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

describe("App", () => {
  it("shows the empty state when there are no pending proposals", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/healthz")) {
        return Promise.resolve(jsonResponse({ status: "ok", demo_mode: true }));
      }
      if (url.includes("/proposals")) {
        return Promise.resolve(jsonResponse({ proposals: [] }));
      }
      return Promise.reject(new Error(`unexpected fetch: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithClient(<App />);

    expect(await screen.findByText(/no pending proposals/i)).toBeInTheDocument();
  });

  it("shows the error state with retry when the API is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("network down"))),
    );

    renderWithClient(<App />);

    expect(await screen.findByText(/can.t reach the server/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
