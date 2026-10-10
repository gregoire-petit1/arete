import { fetchAPI } from "./api";

/** The signed-in athlete's Slack settings (api/slack.py). */
export interface SlackPreferences {
  /** Slack is configured on this server. */
  available: boolean;
  /** A dedicated channel is configured, so channel answers are possible. */
  channel: boolean;
  /** Off: a mention in the channel is answered privately. */
  public_replies: boolean;
}

export const slackApi = {
  preferences: () => fetchAPI<SlackPreferences>("/slack/preferences"),
  setPublicReplies: (public_replies: boolean) =>
    fetchAPI<SlackPreferences>("/slack/preferences", {
      method: "PUT",
      body: JSON.stringify({ public_replies }),
    }),
};
