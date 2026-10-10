// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SlackConnection } from "./SlackConnection";
import { slackApi, type SlackPreferences } from "@/lib/slack";
vi.mock("@/lib/slack", () => ({
  slackApi: { preferences: vi.fn(), setPublicReplies: vi.fn() },
}));
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);
const prefs = (over: Partial<SlackPreferences> = {}): SlackPreferences => ({
  available: true,
  public_replies: false,
  ...over,
});
function mount() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <SlackConnection />
    </QueryClientProvider>,
  );
}
it("keeps channel answers private until the athlete opts in", async () => {
  vi.mocked(slackApi.preferences).mockResolvedValue(prefs());
  vi.mocked(slackApi.setPublicReplies).mockResolvedValue(prefs({ public_replies: true }));
  mount();
  const box = (await screen.findByRole("checkbox", {
    name: /répondre en public/,
  })) as HTMLInputElement;
  expect(box.checked).toBe(false);
  fireEvent.click(box);
  await waitFor(() => expect(vi.mocked(slackApi.setPublicReplies).mock.calls[0]?.[0]).toBe(true));
  await waitFor(() => expect(box.checked).toBe(true));
});
it("shows nothing when Slack is not configured", async () => {
  vi.mocked(slackApi.preferences).mockResolvedValue(prefs({ available: false }));
  const { container } = mount();
  await waitFor(() => expect(slackApi.preferences).toHaveBeenCalled());
  expect(container.innerHTML).toBe("");
});
