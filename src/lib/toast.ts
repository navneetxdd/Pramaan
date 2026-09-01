import { toast } from "sonner";

/** Show an error toast once per id — avoids stacked duplicates on polling/remounts. */
export function toastErrorOnce(id: string, message: string) {
  toast.error(message, { id, duration: 6000 });
}
