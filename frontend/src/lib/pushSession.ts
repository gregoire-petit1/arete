/** Revoke the previous account's device channel before rendering another account. */
export async function claimPushDevice(athleteId: number | null): Promise<void> {
  const key = 'arete.push.athlete';
  const owner = athleteId === null ? '' : String(athleteId);
  if (localStorage.getItem(key) === owner) return;
  if ('serviceWorker' in navigator) {
    const reg = await navigator.serviceWorker.getRegistration();
    const subscription = await reg?.pushManager?.getSubscription();
    if (subscription && !(await subscription.unsubscribe())) {
      throw new Error('Impossible de désactiver les notifications du compte précédent.');
    }
    const notifications = await reg?.getNotifications?.();
    notifications?.forEach((notification) => notification.close());
  }
  localStorage.setItem(key, owner);
}
