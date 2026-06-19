import { useNotificationToasts } from "../hooks/useNotificationToasts";

interface Props {
  apiPrefix: string;
}

/** Polls for new notifications and flashes toast alerts. Renders nothing. */
export default function NotificationToastListener({ apiPrefix }: Props) {
  useNotificationToasts(apiPrefix);
  return null;
}
