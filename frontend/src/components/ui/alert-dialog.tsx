"use client";

import * as React from "react";
import { Button } from "./button";
import { Dialog } from "./dialog";

export interface AlertDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
}

/** تأیید عمل: a blocking confirmation for irreversible actions. Cancel is focused first. */
export function AlertDialog({ open, onOpenChange, title, description, confirmText = "تأیید", cancelText = "انصراف", destructive, onConfirm }: AlertDialogProps) {
  const [busy, setBusy] = React.useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      role="alertdialog"
      title={title}
      description={description}
      className="max-w-sm"
      footer={
        <>
          <Button
            variant={destructive ? "destructive" : "default"}
            loading={busy}
            onClick={async () => {
              setBusy(true);
              try { await onConfirm(); onOpenChange(false); } finally { setBusy(false); }
            }}
          >
            {confirmText}
          </Button>
          <Button variant="outline" data-autofocus disabled={busy} onClick={() => onOpenChange(false)}>{cancelText}</Button>
        </>
      }
    />
  );
}

/** One confirm dialog for destructive page actions. Render `dialog` once. */
export function useConfirm() {
  const [pending, setPending] = React.useState<{ title: string; run: () => void | Promise<void> } | null>(null);
  function ask(title: string, run: () => void | Promise<void>) {
    setPending({ title, run });
  }
  const dialog = (
    <AlertDialog
      open={pending !== null}
      onOpenChange={(open) => { if (!open) setPending(null); }}
      title={pending?.title || "تأیید"}
      confirmText="حذف"
      destructive
      onConfirm={() => pending?.run()}
    />
  );
  return { ask, dialog };
}
